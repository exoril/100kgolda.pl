
import httpx
from app.core.config import PB_URL

_async_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            base_url=PB_URL,
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _async_client

async def close_client():
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
