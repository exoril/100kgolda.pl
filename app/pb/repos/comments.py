from typing import List, Tuple
from app.core.config import COMMENTS_COLLECTION
from app.pb.client import get_client

async def count_comments(post_id: str) -> int:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    params = {"filter": f'post="{post_id}" && approved=true', "perPage": 1, "page": 1}
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return 0
    return int((resp.json() or {}).get("totalItems", 0))


async def add_comment(author: str, email: str, content: str, post_id: str) -> bool:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    payload = {
        "post": post_id,
        "author": author,
        "email": email or "",
        "content": content,
        "approved": True,
    }
    resp = await client.post(url, json=payload)
    return resp.status_code in (200, 201)

async def get_comments_paginated(post_id: str, page: int = 1, per_page: int = 10) -> Tuple[List[dict], int, int]:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    params = {
        "filter": f'post="{post_id}" && approved=true',
        "sort": "-created",
        "page": page,
        "perPage": per_page,
    }
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return [], 0, 0

    data = resp.json() or {}
    items = data.get("items", []) or []
    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page
    return items, total_pages, total_items

async def count_comments(post_id: str) -> int:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    params = {"filter": f'post="{post_id}" && approved=true', "perPage": 1, "page": 1}
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return 0
    return int((resp.json() or {}).get("totalItems", 0))
