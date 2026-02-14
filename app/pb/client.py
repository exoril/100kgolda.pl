# app/pb/client.py
import httpx
import time
import logging
from app.core.config import PB_URL
from app.pb.metrics import record

pb_logger = logging.getLogger("pb")

_async_client: httpx.AsyncClient | None = None


def _path_from_url(url: str) -> str:
    # url bywa "/api/..." albo pełnym "http://.../api/..."
    if not url:
        return ""
    if url.startswith("/"):
        return url
    try:
        return httpx.URL(url).path
    except Exception:
        return url


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
            method = response.request.method
            path = response.request.url.path
            status = response.status_code

            # 1) Twoje metryki do panelu admin
            await record(method=method, path=path, status=status, ms=ms)

            # 2) Log do pb.log (osobny logger)
            pb_logger.info("PB | %s %s | %s | %.1fms", method, path, status, ms)

        _async_client = httpx.AsyncClient(
            base_url=PB_URL,
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"Accept": "application/json"},
            event_hooks={"request": [on_request], "response": [on_response]},
        )

    return _async_client

async def pb_request(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> httpx.Response:
    """
    Zalecane miejsce do wykonywania requestów do PB.

    - sukces: event_hooks zrobi record() + pb_logger.info(...)
    - wyjątek (timeout/connection): tu logujemy + robimy record() ręcznie
    """
    client = await get_client()
    t0 = time.perf_counter()
    path = _path_from_url(url)

    try:
        return await client.request(method, url, params=params, json=json)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000.0

        # status=0 oznacza "brak odpowiedzi" (błąd sieci/timeout)
        await record(method=method, path=path, status=0, ms=ms)

        pb_logger.exception("PB ERROR | %s %s | %.1fms | exc=%r", method, path, ms, e)
        raise


async def close_client() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
