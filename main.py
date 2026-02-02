from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.routes.blog import router as blog_router
from app.routes.pages import router as pages_router
from app.routes.errors import register_error_handlers
from app.pb.client import close_client

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.state.templates = templates

app.include_router(blog_router)
app.include_router(pages_router)

register_error_handlers(app, templates)

@app.on_event("shutdown")
async def shutdown():
    await close_client()

