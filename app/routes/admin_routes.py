from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from app.pb.metrics import snapshot, reset
from app.pb.repos.posts import list_all_post_ids
from app.services.rebuild import rebuild_post_stats
from app.cache import cache

router = APIRouter(prefix="/admin")

@router.post("/rebuild-stats")
async def rebuild_all_stats():
    post_ids = await list_all_post_ids()
    for pid in post_ids:
        await rebuild_post_stats(pid)
    return {"ok": True, "posts": len(post_ids)}

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