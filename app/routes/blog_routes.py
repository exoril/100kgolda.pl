# app/routes/blog_routes.py
from fastapi import APIRouter, Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER
from urllib.parse import quote
from datetime import datetime, timezone

from app.web.render import render_template, render_pagination
from app.web.toc import build_toc
from app.services import blog as blog_service
from app.pb.repos.comments import get_comments_paginated, add_comment
from app.services.recaptcha import verify_recaptcha

router = APIRouter()

COOLDOWN_SECONDS = 300  # 5 min


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
async def post_detail(
    request: Request,
    slug: str,
    cpage: int = Query(1, ge=1),
    captcha: int = Query(0, ge=0, le=1),
    cooldown: int = Query(0, ge=0),
    author: str = Query("", min_length=0),
    email: str = Query("", min_length=0),
):
    post = await blog_service.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    # ✅ visitor id (jedno źródło prawdy) — to samo podejście jak przy komentarzach
    vid = getattr(request.state, "visitor_id", None) or (request.cookies.get("vid") or "").strip()

    # ✅ inkrementuj views tylko jeśli to nowy (post_id, vid) w logu
    if vid:
        await blog_service.register_unique_view(post["id"], vid)

    # buduj TOC (a jeśli chcesz sterować “Komentarze” w TOC — zrobimy później w toc.py)
    post["content"], post["toc"] = build_toc(
        post.get("content", ""),
        include_comments=bool(post.get("comments_on")),
    )

    # ✅ komentarze zależne od posts.comments_on (domyślnie True)
    comments_on = bool(post.get("comments_on", True))

    comments = []
    comments_total_pages = 0
    comments_total_items = 0

    if comments_on:
        comments, comments_total_pages, comments_total_items = await get_comments_paginated(
            post["id"], page=cpage, per_page=10
        )
        if comments_total_pages > 0 and cpage > comments_total_pages:
            raise HTTPException(status_code=404, detail="Strona komentarzy nie istnieje")
    else:
        # jeśli ktoś wepnie ręcznie /post/x?cpage=2 -> 404
        if cpage != 1:
            raise HTTPException(status_code=404, detail="Strona komentarzy nie istnieje")

    response = await render_template(
        request,
        request.app.state.templates,
        "post.html",
        {
            "post": post,
            "comments_on": comments_on,
            "comments": comments,
            "comments_page": cpage,
            "comments_total_pages": comments_total_pages,
            "comments_total_items": comments_total_items,
            "captcha_error": (captcha == 1),
            "cooldown_wait": cooldown,  # jeśli chcesz pokazać toast w JS
            "prefill_author": author,
            "prefill_email": email,
        },
    )

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
    recaptcha_token: str = Form("", alias="g-recaptcha-response"),
):
    author = (author or "").strip()
    content = (content or "").strip()
    email = (email or "").strip()

    if not author or not content:
        return RedirectResponse(url=f"/post/{slug}#comments", status_code=HTTP_303_SEE_OTHER)

    # ✅ CAPTCHA
    ok_captcha = await verify_recaptcha(
        recaptcha_token,
        remote_ip=(request.client.host if request.client else None),
    )
    if not ok_captcha:
        a = quote(author)
        e = quote(email)
        return RedirectResponse(
            url=f"/post/{slug}?captcha=1&author={a}&email={e}#comments",
            status_code=HTTP_303_SEE_OTHER,
        )

    post = await blog_service.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post nie znaleziony")

    # ✅ twarda blokada komentarzy gdy comments_on=False
    if not bool(post.get("comments_on", True)):
        raise HTTPException(status_code=404, detail="Komentarze wyłączone")

    # ✅ visitor id (jedno źródło prawdy)
    vid = getattr(request.state, "visitor_id", None) or (request.cookies.get("vid") or "").strip()

    # ✅ LIMIT 1 komentarz / 5 min na vid
    if vid:
        last_created = await blog_service.get_last_comment_created_for_post(vid, post["id"])
        if last_created is not None:
            now = datetime.now(timezone.utc)
            delta = (now - last_created).total_seconds()
            if delta < COOLDOWN_SECONDS:
                wait = int(COOLDOWN_SECONDS - delta)
                a = quote(author)
                e = quote(email)
                return RedirectResponse(
                    url=f"/post/{slug}?cooldown={wait}&author={a}&email={e}#comments",
                    status_code=HTTP_303_SEE_OTHER,
                )

    ok = await add_comment(
        author=author,
        email=email,
        content=content,
        post_id=post["id"],
        visitor_id=vid or None,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Nie udało się dodać komentarza")

    return RedirectResponse(url=f"/post/{slug}?sent=1#comments", status_code=HTTP_303_SEE_OTHER)
