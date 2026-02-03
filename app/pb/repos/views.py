from app.core.config import POST_VIEWS_COLLECTION
from app.pb.client import get_client

async def count_views(post_id: str) -> int:
    client = await get_client()
    url = f"/api/collections/{POST_VIEWS_COLLECTION}/records"
    params = {"filter": f'post="{post_id}"', "perPage": 1, "page": 1}
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        return 0
    return int((resp.json() or {}).get("totalItems", 0))


async def create_unique_view(post_id: str, day: str, visitor_id: str) -> bool:
    client = await get_client()
    base_url = f"/api/collections/{POST_VIEWS_COLLECTION}/records"

    day_compact = (day or "").replace("-", "")
    visitor_compact = (visitor_id or "").replace("-", "")
    key = f"{post_id}{day_compact}{visitor_compact}"

    # 1) CHECK: czy już istnieje rekord z tym key?
    check_params = {"filter": f'key="{key}"', "perPage": 1, "page": 1}
    check = await client.get(base_url, params=check_params)
    if check.status_code == 200:
        items = (check.json() or {}).get("items") or []
        if items:
            return False  # już naliczone

    # 2) CREATE: jeśli nie ma, utwórz
    payload = {"post": post_id, "day": day, "visitor": visitor_id, "key": key}
    create = await client.post(base_url, json=payload)

    if create.status_code in (200, 201):
        return True

    # fallback: jeśli create się nie udało, nie inkrementujemy
    print("[post_views] create failed:", create.status_code, create.text)
    return False
