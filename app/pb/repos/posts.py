from typing import Any, Dict, List, Tuple, Optional
from app.core.config import POSTS_COLLECTION
from app.pb.client import pb_request
from app.cache import cache, key


def pb_escape(s: str) -> str:
    # Minimalne escapowanie, żeby filtry PB nie padały na cudzysłowach/backslashu
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


async def list_posts(page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    ck = key("posts", "list", page, per_page)
    cached = await cache.get(ck)
    if cached is not None:
        return cached["items"], cached["total_pages"]

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": "published=true",
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json() or {}
    items = data.get("items", []) or []
    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page

    await cache.set(ck, {"items": items, "total_pages": total_pages}, ttl=20)
    return items, total_pages


async def search_posts(q: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    q2 = pb_escape(q)
    ck = key("posts", "search", q2, page, per_page)
    cached = await cache.get(ck)
    if cached is not None:
        return cached["items"], cached["total_pages"]

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": f'published=true && (title ~ "{q2}" || content ~ "{q2}")',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json() or {}
    items = data.get("items", []) or []
    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page

    await cache.set(ck, {"items": items, "total_pages": total_pages}, ttl=20)
    return items, total_pages


async def list_posts_by_category(category: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    cat = pb_escape(category)
    ck = key("posts", "category", cat, page, per_page)
    cached = await cache.get(ck)
    if cached is not None:
        return cached["items"], cached["total_pages"]

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": f'published=true && category="{cat}"',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json() or {}
    items = data.get("items", []) or []
    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page

    await cache.set(ck, {"items": items, "total_pages": total_pages}, ttl=20)
    return items, total_pages


async def get_post_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    s = pb_escape(slug)

    # (opcjonalnie) krótki cache dla detalu posta
    ck = key("posts", "slug", s)
    cached = await cache.get(ck)
    if cached is not None:
        return cached

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": f'slug="{s}" && published=true', "perPage": 1, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return None

    items = (resp.json() or {}).get("items") or []
    post = items[0] if items else None

    if post:
        await cache.set(ck, post, ttl=20)  # krótko, bo content się może zmieniać
    return post


async def get_post_count() -> int:
    ck = key("posts", "count")
    cached = await cache.get(ck)
    if cached is not None:
        return int(cached)

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return 0

    total = int((resp.json() or {}).get("totalItems", 0))
    await cache.set(ck, total, ttl=300)
    return total


async def list_categories() -> List[str]:
    ck = key("posts", "categories")
    cached = await cache.get(ck)
    if cached is not None:
        return cached

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1000, "page": 1, "fields": "category"}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return []

    items = (resp.json() or {}).get("items") or []
    cats = sorted({(p.get("category") or "Bez kategorii") for p in items})

    await cache.set(ck, cats, ttl=600)
    return cats


async def fetch_posts_by_ids(post_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Przydatne do topów: pobierz paczkę postów po ID (bez expand).
    """
    if not post_ids:
        return {}

    # ID z PB zwykle jest bezpieczne, ale escapowanie nie zaszkodzi
    ids = [pb_escape(pid) for pid in post_ids if pid]
    if not ids:
        return {}

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    or_filter = " || ".join([f'id="{pid}"' for pid in ids])
    params = {
        "filter": f"published=true && ({or_filter})",
        "perPage": len(ids),
        "page": 1,
    }
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return {}

    items = (resp.json() or {}).get("items") or []
    return {p["id"]: p for p in items if p.get("id")}


async def list_all_post_ids(per_page: int = 200) -> List[str]:
    """
    Zwraca listę ID wszystkich opublikowanych postów.
    Na start bez paginacji (OK jeśli masz <= per_page postów).
    """
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": "published=true",
        "fields": "id",
        "perPage": per_page,
        "page": 1,
    }
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return []

    items = (resp.json() or {}).get("items") or []
    return [it["id"] for it in items if it.get("id")]
