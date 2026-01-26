from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.web.render import render_template
router = APIRouter()


@router.get("/o-mnie", response_class=HTMLResponse)
async def o_mnie(request: Request):
    return await render_template(request, request.app.state.templates, "o-mnie.html")

@router.get("/moje-projekty", response_class=HTMLResponse)
async def moje_projekty(request: Request):
    return await render_template(request, request.app.state.templates, "moje-projekty.html")

@router.get("/o-blogu", response_class=HTMLResponse)
async def o_blogu(request: Request):
    return await render_template(request, request.app.state.templates, "o-blogu.html")

@router.get("/kontakt", response_class=HTMLResponse)
async def kontakt(request: Request):
    return await render_template(request, request.app.state.templates, "kontakt.html")
