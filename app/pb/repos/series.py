# app/pb/repos/series.py
from typing import Any, Dict
from app.core.config import SERIES_COLLECTION
from app.pb.client import get_client
from app.cache import cache, key

SERIES_TTL = 3600 # sekund (1h)

async def get_series(series_id: str) -> Dict[str, Any]:
    if not series_id:
        return {}
    
    ck = key("series", series_id)
    cached = await cache.get(ck)
    if cached is not None:
        return cached
    
    client = await get_client()
    url = f"/api/collections/{SERIES_COLLECTION}/records/{series_id}"
    resp = await client.get(url)

    if resp.status_code != 200:
        return {}

    data = resp.json() or {}

    out = {
        "id": data.get("id"),
        "suffix": (data.get("suffix") or "").strip(),
        "description": (data.get("description") or "").strip(),
    }

    await cache.set(ck, out, ttl=SERIES_TTL)
    return out

# (opcjonalnie) kompatybilność wstecz
async def get_series_suffix(series_id: str) -> str:
    s = await get_series(series_id)
    return (s.get("suffix") or "").strip()
