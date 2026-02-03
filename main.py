from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.pb.client import close_client
from app.web.render import render_template

from app.routes.blog_routes import router as blog_router
from app.routes.pages import router as pages_router
from app.pb.client import close_client
from app.routes.admin_routes import router as admin_metrics_router
from app.middleware.visitor import VisitorIdMiddleware

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

@app.on_event("shutdown")
async def _shutdown():
    await close_client()
