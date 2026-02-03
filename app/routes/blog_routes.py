from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi import Form
from starlette.status import HTTP_303_SEE_OTHER
from pydantic import BaseModel

from app.web.render import render_template
from app.web.toc import build_toc
from app.services import blog as blog_service
from app.services.counters import count_unique_view, sync_comments_total
from app.pb.repos.comments import get_comments_paginated, add_comment
from app.web.render import render_template, render_pagination
from urllib.parse import quote

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = Query(1, ge=1)):
    posts, total_pages = await blog_service.list_posts(page=page, per_page=5)

    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    pagination_html = render_pagination(
        request=request,
        templates=request.app.state.templates,
        page=page,
        total_pages=total_pages,
        base_url="/",
    )

    return await render_template(
        request=request,
        templates=request.app.state.templates,
        template_name="index.html",
        context={
            "posts": posts,
            "page": page,
            "total_pages": total_pages,
            "pagination_html": pagination_html,
            "context_name": None,
        },
    )


@router.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(request: Request, slug: str, cpage: int = Query(1, ge=1)):
    post = await blog_service.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    post["content"], post["toc"] = build_toc(post.get("content", ""))

    comments, comments_total_pages, comments_total_items = await get_comments_paginated(
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

    await count_unique_view(request, response, post["id"])
    return response


@router.get("/kategorie/{slug}", response_class=HTMLResponse)
async def category_page(request: Request, slug: str, page: int = Query(1, ge=1)):
    categories = await blog_service.get_all_categories()

    if slug not in categories:
        raise HTTPException(status_code=404, detail="Kategoria nie znaleziona")

    posts, total_pages = await blog_service.posts_by_category(slug, page=page, per_page=5)

    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    pagination_html = render_pagination(
        request=request,
        templates=request.app.state.templates,
        page=page,
        total_pages=total_pages,
        base_url=f"/kategorie/{slug}",
    )

    return await render_template(
        request=request,
        templates=request.app.state.templates,
        template_name="kategorie.html",
        context={
            "categories": categories,
            "selected_category": slug,
            "posts": posts,
            "pagination_html": pagination_html,
            "page": page,
            "total_pages": total_pages,
        },
    )

@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query("", min_length=0),
    page: int = Query(1, ge=1),
):
    # ❗Odrzuć błędne URL-e typu: /search?q=asd?page=2
    # (wtedy "page=2" ląduje w q, a nie w parametrze page)
    if q and "page=" in q:
        raise HTTPException(status_code=404, detail="Strona nie istnieje")

    posts = []
    total_pages = 0
    pagination_html = ""

    if q:
        posts, total_pages = await blog_service.search_posts(q, page=page, per_page=5)

        if total_pages > 0 and page > total_pages:
            raise HTTPException(status_code=404, detail="Strona nie istnieje")

        base_url = f"/search?q={quote(q)}"
        pagination_html = render_pagination(
            request=request,
            templates=request.app.state.templates,
            page=page,
            total_pages=total_pages,
            base_url=base_url,
        )

    return await render_template(
        request=request,
        templates=request.app.state.templates,
        template_name="search.html",
        context={
            "query": q,
            "posts": posts,
            "pagination_html": pagination_html,
            "page": page,
            "total_pages": total_pages,
        },
    )

@router.post("/post/{slug}/comment")
async def add_comment_route(
    request: Request,
    slug: str,
    author: str = Form(...),
    email: str = Form(None),
    content: str = Form(...),
):
    author = (author or "").strip()
    content = (content or "").strip()
    email = (email or "").strip()

    if not author or not content:
        return RedirectResponse(url=f"/post/{slug}", status_code=HTTP_303_SEE_OTHER)

    post = await blog_service.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    visitor_id = getattr(request.state, "visitor_id", None)

    ok = await add_comment(
        author=author,
        email=email,
        content=content,
        post_id=post["id"],
        visitor_id=visitor_id,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Nie udało się dodać komentarza")

    await sync_comments_total(post["id"])
    return RedirectResponse(url=f"/post/{slug}", status_code=HTTP_303_SEE_OTHER)
