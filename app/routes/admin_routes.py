from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from app.pb.metrics import snapshot, reset
from app.cache import cache

router = APIRouter(prefix="/admin")

@router.get("/metrics.json")
async def metrics_json():
    return JSONResponse(await snapshot())

@router.post("/metrics/reset")
async def metrics_reset():
    await reset()
    return {"ok": True}

@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    data = await snapshot()
    # render przez Twoje templates (layout może zostać)
    templates = request.app.state.templates
    return templates.TemplateResponse("admin/metrics.html", {"request": request, "m": data})


@router.get("/cache.json")
async def cache_json():
    return await cache.snapshot()