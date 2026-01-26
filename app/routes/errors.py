from fastapi import Request
from starlette import status
from fastapi.templating import Jinja2Templates
from app.web.render import render_template

def register_error_handlers(app, templates: Jinja2Templates):
    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        resp = await render_template(
            request,
            templates,
            "404.html",
            {"context_name": None},
        )
        resp.status_code = status.HTTP_404_NOT_FOUND
        return resp
