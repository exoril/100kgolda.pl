from app.core.config import POSTS_COLLECTION, POST_STATS_COLLECTION
from app.pb.cache import cache_get, cache_set
from app.pb.client import get_client
from app.pb.normalize import normalize_post
from app.pb.comments import get_comment_count_for_post
import asyncio
from typing import Dict, Any

DEFAULT_STATS: Dict[str, int] = {
    "views_total": 0,
    "comments_total": 0,
    "reactions_like": 0,
    "reactions_love": 0,
    "reactions_laugh": 0,
}

async def get_top_viewed_posts(limit: int = 3):
    cache_key = f"top_posts:{limit}"
    cached = cache_get(cache_key, ttl=60)
    if cached is not None:
        return cached
    
    # DEBUGOWANIE CACHE
    print("CACHE MISS: " + cache_key )

    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": "published=true",
        "sort": "-views",
        "perPage": limit,
        "page": 1,
        "fields": "id,title,slug,category,created,thumbnail,views,content,creator,series",
    }

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return []

    items = resp.json().get("items", [])
    posts = [await normalize_post(post) for post in items]

    cache_set(cache_key, posts)
    return posts

async def search_posts_simple(query: str, page: int = 1, per_page: int = 5):
    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": f'published=true && (title ~ "{query}" || content ~ "{query}")',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json()
    items = data.get("items", [])
    total_items = data.get("totalItems", 0)
    total_pages = (total_items + per_page - 1) // per_page

    posts = [await normalize_post(post) for post in items]
    return posts, total_pages


async def get_post_count() -> int:
    cache_key = "post_count"
    cached = cache_get(cache_key, ttl=60)
    if cached is not None:
        return cached

    # DEBUGOWANIE CACHE
    print("CACHE MISS: " + cache_key )

    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1}

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return 0

    total = resp.json().get("totalItems", 0)
    cache_set(cache_key, total)
    return total
from typing import Dict, Any, Optional


async def _get_post_stats_by_post_id(client, post_id: str) -> Optional[Dict[str, Any]]:
    url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    params = {"filter": f'post = "{post_id}"', "perPage": 1, "page": 1}

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        print("Błąd pobierania post_stats:", resp.text)
        return None

    items = (resp.json() or {}).get("items") or []
    return items[0] if items else None


async def _create_post_stats(client, post_id: str) -> Optional[Dict[str, Any]]:
    url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    payload = {"post": post_id, **DEFAULT_STATS}

    resp = await client.post(url, json=payload)
    # PocketBase zwykle zwraca 200 albo 201 po create (zależnie od wersji / proxy)
    if resp.status_code not in (200, 201):
        print("Błąd tworzenia post_stats:", resp.text)
        return None

    return resp.json()


async def get_post_by_slug(slug: str):
    client = await get_client()

    # 1) POST
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": f'slug = "{slug}"', "perPage": 1, "page": 1}

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        print("Błąd pobierania posta:", resp.text)
        return None

    items = resp.json().get("items") or []
    if not items:
        return None

    # ✅ normalize_post ZAWSZE
    post = await normalize_post(items[0])

    # 2) STATS: spróbuj pobrać
    stats_url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    stats_params = {"filter": f'post = "{post["id"]}"', "perPage": 1, "page": 1}

    stats_resp = await client.get(stats_url, params=stats_params)
    stats = None
    if stats_resp.status_code == 200:
        stats_items = (stats_resp.json() or {}).get("items") or []
        if stats_items:
            stats = stats_items[0]

    # 3) STATS: jak nie ma, to utwórz
    if not stats:
        create_resp = await client.post(
            f"/api/collections/{POST_STATS_COLLECTION}/records",
            json={"post": post["id"], **DEFAULT_STATS},
        )

        if create_resp.status_code in (200, 201):
            stats = create_resp.json()
        else:
            # fallback: jeszcze raz pobierz (race condition)
            retry = await client.get(stats_url, params=stats_params)
            if retry.status_code == 200:
                retry_items = (retry.json() or {}).get("items") or []
                if retry_items:
                    stats = retry_items[0]

            if not stats:
                print("Błąd tworzenia post_stats:", create_resp.text)
                stats = DEFAULT_STATS.copy()

    # 4) doklej do posta
    post["stats"] = stats
    return post


from typing import Dict, Any, List

POST_STATS_COLLECTION = "post_stats"

DEFAULT_STATS: Dict[str, int] = {
    "views_total": 0,
    "comments_total": 0,
    "reactions_like": 0,
    "reactions_love": 0,
    "reactions_laugh": 0,
}

async def get_all_posts(page: int = 1, per_page: int = 5):
    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": "published=true",
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json()
    items = data.get("items", [])
    total_items = data.get("totalItems", 0)
    total_pages = (total_items + per_page - 1) // per_page

    # ✅ zawsze normalize_post
    posts: List[Dict[str, Any]] = [await normalize_post(post) for post in items]

    # ---- doklej stats (get-or-create dla listy) ----
    post_ids = [p.get("id") for p in posts if p.get("id")]
    if not post_ids:
        return posts, total_pages

    # 1) pobierz wszystkie stats dla tych postów w jednym zapytaniu
    # PocketBase filter: OR przez ||
    or_filter = " || ".join([f'post = "{pid}"' for pid in post_ids])
    stats_url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    stats_params = {"filter": or_filter, "perPage": len(post_ids), "page": 1}

    stats_resp = await client.get(stats_url, params=stats_params)

    stats_by_post_id: Dict[str, Dict[str, Any]] = {}
    if stats_resp.status_code == 200:
        stats_items = (stats_resp.json() or {}).get("items") or []
        for s in stats_items:
            # relacja "post" w rekordzie statów powinna być ID posta (string)
            pid = s.get("post")
            if pid:
                stats_by_post_id[pid] = s

    # 2) dla brakujących — utwórz rekordy
    missing_ids = [pid for pid in post_ids if pid not in stats_by_post_id]

    for pid in missing_ids:
        create_resp = await client.post(
            f"/api/collections/{POST_STATS_COLLECTION}/records",
            json={"post": pid, **DEFAULT_STATS},
        )
        if create_resp.status_code in (200, 201):
            created = create_resp.json()
            stats_by_post_id[pid] = created
        else:
            # fallback: jeśli nie udało się utworzyć, daj domyślne
            stats_by_post_id[pid] = DEFAULT_STATS.copy()

    # 3) doklej do postów
    for p in posts:
        pid = p.get("id")
        p["stats"] = stats_by_post_id.get(pid, DEFAULT_STATS.copy())
    # -----------------------------------------------

    return posts, total_pages


async def get_all_categories():
    cache_key = "all_categories"
    cached = cache_get(cache_key, ttl=300)
    if cached is not None:
        return cached
    
    # DEBUGOWANIE CACHE
    print("CACHE MISS: " + cache_key )

    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1000, "fields": "category"}

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return []

    items = resp.json().get("items", [])
    categories = sorted(set(post.get("category", "Bez kategorii") for post in items))

    cache_set(cache_key, categories)
    return categories


async def get_posts_by_category(category: str, page: int = 1, per_page: int = 5):
    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": f'published=true && category="{category}"',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json()
    items = data.get("items", [])
    total_items = data.get("totalItems", 0)
    total_pages = (total_items + per_page - 1) // per_page

    posts = [await normalize_post(post) for post in items]
    return posts, total_pages

async def get_top_commented_posts(limit: int = 3, scan: int = 50):
    """
    Bierze ostatnie `scan` postów, liczy komentarze, sortuje i zwraca top `limit`.
    Cache na 60s.
    """
    cache_key = f"top_commented:{limit}:{scan}"
    cached = cache_get(cache_key, ttl=60)
    if cached is not None:
        return cached

    print("CACHE MISS: " + cache_key)

    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": "published=true",
        "sort": "-created",
        "perPage": scan,
        "page": 1,
        "fields": "id,title,slug,category,created,thumbnail,views,content,creator,series",
    }

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return []

    items = resp.json().get("items", [])
    posts = [await normalize_post(p) for p in items]

    # policz komentarze równolegle
    counts = await asyncio.gather(*[get_comment_count_for_post(p["id"]) for p in posts])

    # dopnij count do postów
    for p, c in zip(posts, counts):
        p["comment_count"] = c

    # sort i top
    posts.sort(key=lambda x: x.get("comment_count", 0), reverse=True)
    top = posts[:limit]

    cache_set(cache_key, top)
    return top

