from app.core.config import COMMENTS_COLLECTION
from app.pb.client import get_client
from app.pb.cache import cache_set, cache_get
from typing import List, Tuple

async def get_comments_by_post_id(post_id: str) -> List[dict]:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    params = {
        "filter": f'post="{post_id}" && approved=true',
        "sort": "-created",
    }
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return []
    return resp.json().get("items", [])

async def get_comment_count_for_post(post_id: str) -> int:
    cache_key = f"comment_count:{post_id}"
    cached = cache_get(cache_key, ttl=30)
    if cached is not None:
        return cached
    
    # DEBUGOWANIE CACHE
    print("CACHE MISS: " + cache_key )

    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"
    params = {
        "filter": f'post = "{post_id}" && approved=true',
        "perPage": 1
    }
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return 0

    total_items = resp.json().get("totalItems", 0)
    cache_set(cache_key, total_items)
    return total_items


async def add_comment_simple(author: str, email: str, content: str, post_id: str) -> bool:
    client = await get_client()
    url = f"/api/collections/{COMMENTS_COLLECTION}/records"

    payload = {
        "post": post_id,
        "author": author,
        "email": email,
        "content": content,
        "approved": True,
    }

    resp = await client.post(url, json=payload)

    if resp.status_code != 200:
        print("Błąd zapisu komentarza:", resp.status_code, resp.text)
        return False

    return True

async def get_comments_by_post_id_paginated(
    post_id: str,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int, int]:
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

    data = resp.json()
    items = data.get("items", [])
    total_items = int(data.get("totalItems", 0))
    total_pages = (total_items + per_page - 1) // per_page

    return items, total_pages, total_items