from app.core.config import POSTS_COLLECTION
from app.pb.cache import cache_get, cache_set
from app.pb.client import get_client
from app.pb.normalize import normalize_post
from app.pb.comments import get_comment_count_for_post
import asyncio

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


async def increment_post_views(post_id: str):
    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records/{post_id}"

    resp = await client.get(url)
    if resp.status_code != 200:
        print("Nie udało się pobrać posta do inkrementacji")
        return

    data = resp.json()
    current_views = data.get("views", 0)

    payload = {"views": current_views + 1}

    resp2 = await client.patch(url, json=payload)
    if resp2.status_code != 200:
        print("Błąd przy zapisie views:", resp2.text)


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


async def get_post_by_slug(slug: str):
    client = await get_client()
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": f'slug = "{slug}"', "perPage": 1}

    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        print("Błąd pobierania posta")
        return None

    items = resp.json().get("items")
    if not items:
        return None

    return await normalize_post(items[0])


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

    posts = [await normalize_post(post) for post in items]
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