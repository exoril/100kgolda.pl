from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException, status
from pocketbase import *
from fastapi import Query

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

from jinja2 import Template

def render_pagination(request: Request, page: int, total_pages: int, base_url: str) -> str:
    """
    Renderuje partial pagination.html z przekazanymi zmiennymi.
    Zwraca HTML jako string.
    """
    return templates.get_template("partials/pagination.html").render(
        page=page,
        total_pages=total_pages,
        base_url=base_url,
        request=request   # w razie gdy partial używa {{ request }}
    )


@app.get("/post/{slug}", response_class=HTMLResponse)
def post_detail(request: Request, slug: str):
    slug_decoded = slug  # FastAPI automatycznie dekoduje URL
    post = get_post_by_slug(slug_decoded)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")
    return templates.TemplateResponse("post.html", {"request": request, "post": post})


@app.get("/", response_class=HTMLResponse)
def index(request: Request, page: int = Query(1, ge=1)):
    posts, total_pages = get_all_posts(page)
    pagination_html = render_pagination(request, page, total_pages, base_url="/")
    
    return templates.TemplateResponse("index.html", {
            "request": request,
            "posts": posts,
            "page": page,
            "total_pages": total_pages,
            "pagination_html": pagination_html,
})


@app.get("/kategorie", response_class=HTMLResponse)
def categories_root(request: Request):
    categories = get_all_categories()
    return templates.TemplateResponse(
        "kategorie.html",
        {
            "request": request,
            "categories": categories,
            "posts": [],          # brak postów na starcie
            "selected_category": None
        }
    )

from fastapi import HTTPException, Query

@app.get("/kategorie/{slug}", response_class=HTMLResponse)
def category_page(request: Request, slug: str, page: int = Query(1, ge=1)):
    categories = get_all_categories()

    # sprawdzamy czy kategoria istnieje
    if slug not in categories:
        raise HTTPException(status_code=404, detail="Kategoria nie znaleziona")

    # pobieramy posty z paginacją
    posts, total_pages = get_posts_by_category(slug, page)

    # jeśli podana strona > total_pages, 404
    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    # generujemy HTML paginacji
    pagination_html = render_pagination(request, page, total_pages, base_url=f"/kategorie/{slug}")

    return templates.TemplateResponse("kategorie.html", {
        "request": request,
        "categories": categories,
        "selected_category": slug,
        "posts": posts,
        "pagination_html": pagination_html,
        "page": page,
        "total_pages": total_pages,
    })


@app.get("/o-mnie", response_class=HTMLResponse)
def o_mnie(request: Request):
    return templates.TemplateResponse(
        "o-mnie.html",
        {"request": request}
    )


@app.get("/o-blogu", response_class=HTMLResponse)
def o_blogu(request: Request):
    return templates.TemplateResponse(
        "o-blogu.html",
        {"request": request}
    )


@app.get("/kontakt", response_class=HTMLResponse)
def kontakt(request: Request):
    return templates.TemplateResponse(
        "kontakt.html",
        {"request": request}
    )

# 404 handler
@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "404.html",
        {"request": request},
        status_code=status.HTTP_404_NOT_FOUND
    )