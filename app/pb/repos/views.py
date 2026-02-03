from app.core.config import POST_VIEWS_COLLECTION
from app.pb.client import pb_request

def pb_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


async def count_views(post_id: str) -> int:
    url = f"/api/collections/{POST_VIEWS_COLLECTION}/records"
    pid = pb_escape(post_id)
    params = {"filter": f'post="{pid}"', "perPage": 1, "page": 1}

    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return 0

    return int((resp.json() or {}).get("totalItems", 0))


async def create_unique_view(post_id: str, day: str, visitor_id: str) -> bool:
    """
    Nalicz 1 view / post / visitor / day.
    Zwraca True tylko gdy UTWORZYŁ nowy rekord.
    Jeśli rekord już istnieje (unikalny key) -> False.
    """
    url = f"/api/collections/{POST_VIEWS_COLLECTION}/records"

    day_compact = (day or "").replace("-", "")
    visitor_compact = (visitor_id or "").replace("-", "")
    # post_id z PB zwykle jest bezpieczne, ale dla spójności:
    post_compact = (post_id or "").replace(":", "").strip()

    key = f"{post_compact}:{day_compact}:{visitor_compact}"

    payload = {
        "post": post_id,
        "day": day,
        "visitor_id": visitor_id,   # pole w kolekcji views
        "key": key,
    }

    resp = await pb_request("POST", url, json=payload)
    if resp.status_code in (200, 201):
        return True

    # Duplikat unique(key) -> już naliczone
    if resp.status_code == 400:
        return False

    print("[post_views] create failed:", resp.status_code, resp.text)
    return False
