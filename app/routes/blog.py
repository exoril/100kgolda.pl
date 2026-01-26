from urllib.parse import quote
from fastapi import APIRouter, Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER
from app.web.render import render_template, render_pagination
from app.web.toc import build_toc
from app.pb.posts import (
    get_post_by_slug,
    increment_post_views,
    get_all_posts,
    get_all_categories,
    get_posts_by_category,
    search_posts_simple
)
from app.pb.comments import (
    add_comment_simple,
    get_comments_by_post_id_paginated
)

router = APIRouter()

# =========================
# KOMENTARZE
# =========================
@router.post("/post/{slug}/comment")
async def add_comment(
    request: Request,  # dodajemy request, bo to FastAPI/Starlette i tak lubi mieć kontekst
    slug: str,
    author: str = Form(...),
    email: str = Form(None),
    content: str = Form(...),
):
    author = author.strip()
    content = content.strip()
    email = email.strip() if email else ""

    if not author or not content:
        return RedirectResponse(url=f"/post/{slug}", status_code=HTTP_303_SEE_OTHER)

    post = await get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    ok = await add_comment_simple(
        author=author,
        email=email,
        content=content,
        post_id=post["id"],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Nie udało się dodać komentarza")

    return RedirectResponse(url=f"/post/{slug}", status_code=HTTP_303_SEE_OTHER)


# =========================
# POST DETAIL
# =========================
@router.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(request: Request, slug: str, cpage: int = Query(1, ge=1)):
    post = await get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    post["content"], post["toc"] = build_toc(post.get("content", ""))

    comments, comments_total_pages, comments_total_items = await get_comments_by_post_id_paginated(
        post["id"], page=cpage, per_page=10
    )

    if comments_total_pages > 0 and cpage > comments_total_pages:
        raise HTTPException(status_code=404, detail="Strona komentarzy nie istnieje")

    response = await render_template(request, request.app.state.templates, "post.html", {
        "post": post,
        "comments": comments,
        "comments_page": cpage,
        "comments_total_pages": comments_total_pages,
        "comments_total_items": comments_total_items,
    })

    cookie_name = f"viewed_post_{post['id']}"
    if not request.cookies.get(cookie_name):
        await increment_post_views(post["id"])
        post["views"] += 1
        response.set_cookie(
            key=cookie_name,
            value="1",
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="lax",
        )

    return response


# =========================
# INDEX
# =========================
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = Query(1, ge=1)):
    posts, total_pages = await get_all_posts(page)

    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    pagination_html = render_pagination(
        request,
        request.app.state.templates,
        page,
        total_pages,
        base_url="/",
    )

    return await render_template(request, request.app.state.templates, "index.html", {
        "posts": posts,
        "page": page,
        "total_pages": total_pages,
        "pagination_html": pagination_html,
        "context_name": None,
    })


# =========================
# KATEGORIE
# =========================

@router.get("/kategorie/{slug}", response_class=HTMLResponse)
async def category_page(request: Request, slug: str, page: int = Query(1, ge=1)):
    categories = await get_all_categories()

    if slug not in categories:
        raise HTTPException(status_code=404, detail="Kategoria nie znaleziona")

    posts, total_pages = await get_posts_by_category(slug, page)

    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    pagination_html = render_pagination(
        request,
        request.app.state.templates,
        page,
        total_pages,
        base_url=f"/kategorie/{slug}",
    )

    return await render_template(request, request.app.state.templates, "kategorie.html", {
        "categories": categories,
        "selected_category": slug,
        "posts": posts,
        "pagination_html": pagination_html,
        "page": page,
        "total_pages": total_pages,
    })


# =========================
# SEARCH
# =========================
@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("", min_length=0), page: int = Query(1, ge=1)):
    posts = []
    total_pages = 0
    pagination_html = ""

    if q:
        posts, total_pages = await search_posts_simple(q, page)

        if total_pages > 0 and page > total_pages:
            raise HTTPException(status_code=404, detail="Strona nie istnieje")

        base_url = f"/search?q={quote(q)}"
        pagination_html = render_pagination(
            request,
            request.app.state.templates,
            page,
            total_pages,
            base_url=base_url,
        )

    return await render_template(request, request.app.state.templates, "search.html", {
        "query": q,
        "posts": posts,
        "pagination_html": pagination_html,
        "page": page,
        "total_pages": total_pages,
    })
