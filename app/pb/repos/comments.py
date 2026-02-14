from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import COMMENTS_COLLECTION
from app.pb.client import pb_request

WARSAW = ZoneInfo("Europe/Warsaw")

def pb_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')

def format_dt_pl_warsaw(dt_str: str) -> str:
    if not dt_str:
        return ""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))  # aware UTC
    dt = dt.astimezone(WARSAW)
    return dt.strftime("%d.%m.%Y %H:%M")

async def count_comments(post_id: str) -> int:
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    pid = pb_escape(post_id)
    params = {"filter": f'post="{pid}" && approved=true', "perPage": 1, "page": 1}
    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return 0
    return int((resp.json() or {}).get("totalItems", 0))

async def add_comment(
    author: str,
    email: str,
    content: str,
    post_id: str,
    visitor_id: Optional[str],
) -> bool:
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"

    payload: Dict[str, Any] = {
        "post": post_id,
        "author": author,
        "email": email or "",
        "content": content,
        "approved": True,
    }
    if visitor_id:
        payload["visitor_id"] = visitor_id

    resp = await pb_request("POST", url, json=payload)  # ✅ POST
    return resp.status_code in (200, 201)


async def get_comments_paginated(
    post_id: str,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int, int]:
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    pid = pb_escape(post_id)
    params = {
        "filter": f'post="{pid}" && approved=true',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }

    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return [], 0, 0

    data = resp.json() or {}
    items = data.get("items", []) or []

    # ✅ dopiszmy czas PL (Warszawa) do każdego komentarza
    for c in items:
        c["created_pl"] = format_dt_pl_warsaw(c.get("created"))

    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page
    return items, total_pages, total_items
