# app/pb/client.py
import httpx
import time
from app.core.config import PB_URL
from app.pb.metrics import record

_async_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    global _async_client

    if _async_client is None:

        async def on_request(request: httpx.Request):
            request.extensions["t0"] = time.perf_counter()

        async def on_response(response: httpx.Response):
            t0 = response.request.extensions.get("t0")
            if t0 is None:
                return
            ms = (time.perf_counter() - t0) * 1000.0
            await record(
                method=response.request.method,
                path=response.request.url.path,
                status=response.status_code,
                ms=ms,
            )

        _async_client = httpx.AsyncClient(
            base_url=PB_URL,
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"Accept": "application/json"},
            event_hooks={"request": [on_request], "response": [on_response]},
        )

    return _async_client


async def close_client() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
