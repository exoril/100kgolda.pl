from typing import Any, Dict, List, Tuple, Optional
from app.core.config import POSTS_COLLECTION, PB_URL
from app.pb.client import pb_request
import httpx

def pb_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')

async def pb_increment_post_views(post_id: str) -> None:
    """
    Inkrementuje pole `views` w rekordzie posta w PocketBase o 1.
    (Prosta wersja: GET aktualnej wartości -> PATCH +1)
    """
    if not post_id:
        return

    async with httpx.AsyncClient(timeout=5) as client:
        # 1) Pobierz aktualny rekord (żeby poznać current views)
        r = await client.get(f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records/{post_id}")
        r.raise_for_status()
        post = r.json()

        current = int(post.get("views") or 0)

        # 2) Zapisz +1
        r2 = await client.patch(
            f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records/{post_id}",
            json={"views": current + 1},
        )
        r2.raise_for_status()


async def list_posts(page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
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

    return items, total_pages


async def search_posts(q: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    q2 = pb_escape(q)

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

    return items, total_pages


async def list_posts_by_category(category: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    cat = pb_escape(category)

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

    return items, total_pages


async def get_post_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    s = pb_escape(slug)

    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": f'slug="{s}" && published=true', "perPage": 1, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return None

    items = (resp.json() or {}).get("items") or []
    post = items[0] if items else None

    return post


async def get_post_count() -> int:
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return 0

    total = int((resp.json() or {}).get("totalItems", 0))
    return total


async def list_categories() -> List[str]:
    url = f"/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1000, "page": 1, "fields": "category"}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return []

    items = (resp.json() or {}).get("items") or []
    cats = sorted({(p.get("category") or "Bez kategorii") for p in items})

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
