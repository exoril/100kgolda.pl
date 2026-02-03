import asyncio
from typing import Any, Dict, List

from app.core.config import POST_STATS_COLLECTION
from app.pb.client import pb_request
from app.cache import cache, key

DEFAULT_STATS: Dict[str, int] = {
    "views_total": 0,
    "comments_total": 0,
}


def pb_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


async def update_stats_totals(post_id: str, views_total: int, comments_total: int) -> None:
    stats_map = await ensure_stats_for_posts([post_id])
    stats = stats_map.get(post_id) or {}
    sid = stats.get("id")
    if not sid:
        return

    payload = {
        "views_total": int(views_total),
        "comments_total": int(comments_total),
    }

    url = f"/api/collections/{POST_STATS_COLLECTION}/records/{sid}"
    await pb_request("PATCH", url, json=payload)

    # odśwież cache dla pojedynczego posta
    await cache.delete(key("stats", "one", post_id))


async def get_stats_map(post_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not post_ids:
        return {}

    # cache key musi zależeć od zestawu ID (kolejność nie powinna mieć znaczenia)
    ids_sorted = sorted({pid for pid in post_ids if pid})
    if not ids_sorted:
        return {}

    ck = key("stats", "map", ",".join(ids_sorted))
    cached = await cache.get(ck)
    if cached is not None:
        return cached

    url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    or_filter = " || ".join([f'post="{pb_escape(pid)}"' for pid in ids_sorted])
    params = {"filter": or_filter, "perPage": len(ids_sorted), "page": 1}

    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return {}

    items = (resp.json() or {}).get("items") or []
    out: Dict[str, Dict[str, Any]] = {}
    for s in items:
        pid = s.get("post")
        if pid:
            out[pid] = s

    # lekki TTL — stats zmieniają się (views), więc 10–20s
    await cache.set(ck, out, ttl=10)
    return out


async def ensure_stats_for_posts(post_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Zwraca mapę stats dla post_ids. Brakujące tworzy (równolegle).
    """
    ids = [pid for pid in post_ids if pid]
    if not ids:
        return {}

    stats_map = await get_stats_map(ids)
    missing = [pid for pid in ids if pid not in stats_map]
    if not missing:
        return stats_map

    async def _create(pid: str):
        url = f"/api/collections/{POST_STATS_COLLECTION}/records"
        resp = await pb_request("POST", url, json={"post": pid, **DEFAULT_STATS})
        if resp.status_code in (200, 201):
            return pid, (resp.json() or {})
        return pid, DEFAULT_STATS.copy()

    created = await asyncio.gather(*[_create(pid) for pid in missing])
    for pid, stats in created:
        stats_map[pid] = stats

    # nie próbuję tu usuwać map-cache (bo nie znam Twojego cache API na prefix),
    # TTL=10s i tak szybko się zaktualizuje.
    return stats_map


async def get_or_create_stats(post_id: str) -> Dict[str, Any]:
    if not post_id:
        return {"post": post_id, **DEFAULT_STATS}

    ck = key("stats", "one", post_id)
    cached = await cache.get(ck)
    if cached is not None:
        return cached

    m = await ensure_stats_for_posts([post_id])
    out = m.get(post_id) or {"post": post_id, **DEFAULT_STATS}

    # bardzo krótko, bo to używają updatery
    await cache.set(ck, out, ttl=5)
    return out


async def update_comments_total(post_id: str, new_count: int) -> None:
    stats = await get_or_create_stats(post_id)
    sid = stats.get("id")
    if not sid:
        return

    url = f"/api/collections/{POST_STATS_COLLECTION}/records/{sid}"
    await pb_request("PATCH", url, json={"comments_total": int(new_count)})

    await cache.delete(key("stats", "one", post_id))


async def increment_views_total(post_id: str, by: int = 1) -> None:
    """
    Read-modify-write (na blogowy ruch wystarczy i jest proste).
    """
    stats = await get_or_create_stats(post_id)
    sid = stats.get("id")
    if not sid:
        return

    current = int(stats.get("views_total", 0))
    url = f"/api/collections/{POST_STATS_COLLECTION}/records/{sid}"
    await pb_request("PATCH", url, json={"views_total": current + int(by)})

    await cache.delete(key("stats", "one", post_id))


async def list_stats_sorted(stat_field: str, limit: int = 50) -> List[Dict[str, Any]]:
    # (opcjonalny cache na topy)
    ck = key("stats", "sorted", stat_field, limit)
    cached = await cache.get(ck)
    if cached is not None:
        return cached

    url = f"/api/collections/{POST_STATS_COLLECTION}/records"
    params = {"sort": f"-{pb_escape(stat_field)}", "perPage": limit, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return []

    items = (resp.json() or {}).get("items") or []
    await cache.set(ck, items, ttl=10)  # topy mogą być cache'owane krótko
    return items
