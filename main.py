from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging
import uuid

from app.pb.client import close_client
from app.web.render import render_template

from app.routes.blog_routes import router as blog_router
from app.routes.pages import router as pages_router
from app.routes.admin_routes import router as admin_metrics_router
from app.middleware.visitor import VisitorIdMiddleware
from app.core.logging import setup_logging

logger = logging.getLogger("app")

setup_logging()

app = FastAPI()

app.add_middleware(VisitorIdMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.state.templates = templates

app.include_router(blog_router)
app.include_router(pages_router)
app.include_router(admin_metrics_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return await render_template(request, app.state.templates, "404.html", {})
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    error_id = "ERR-" + uuid.uuid4().hex[:8]

    # log ze stack trace + error_id
    logger.exception("[%s] Unhandled error: %s %s", error_id, request.method, request.url)

    # API -> JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal Server Error", "error_id": error_id}, status_code=500)

    # HTML -> 500.html
    return await render_template(request, app.state.templates, "500.html", {
        "path": str(request.url.path),
        "error_id": error_id,
    })

@app.on_event("shutdown")
async def _shutdown():
    await close_client()
