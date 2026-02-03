from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.web.render import render_template

router = APIRouter()

@router.get("/404", response_class=HTMLResponse)
async def not_found_page(request: Request):
    # pomocnicza strona, gdybyś chciał link/test
    return await render_template(request, request.app.state.templates, "404.html", {})
