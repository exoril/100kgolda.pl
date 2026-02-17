from __future__ import annotations
from fastapi import APIRouter, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from urllib.parse import quote_plus
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime, timezone
from html import unescape
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from app.config import (
    PB_URL,
    RECAPTCHA_SITE_KEY,
    RECAPTCHA_SECRET_KEY,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    CONTACT_TO,
    CONTACT_FROM,
)
import secrets
import httpx
import uuid
import re
import unicodedata

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.state.templates = templates
templates.env.filters["urlencode"] = lambda s: quote_plus(str(s))

router = APIRouter()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        base = await public_context(request)  # <-- widgety
        return app.state.templates.TemplateResponse(
            "404.html",
            {"request": request, **base, "context_name": "404"},
            status_code=404,
        )

    return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex[:10]
    print(f"500 ERROR [{error_id}]:", repr(exc))

    base = await public_context(request)  # <-- widgety
    return app.state.templates.TemplateResponse(
        "500.html",
        {"request": request, **base, "error_id": error_id, "context_name": "500"},
        status_code=500,
    )


def pb_escape(s: str) -> str:
    # PocketBase filter używa cudzysłowów -> uciekamy "
    return (s or "").replace('"', '\\"').strip()


_TAG_RE = re.compile(r"<[^>]+>")
_IMG_TAG_RE = re.compile(r"<img\b([^>]*?)>", re.IGNORECASE)
_LOADING_RE = re.compile(r"\bloading\s*=\s*(['\"]).*?\1", re.IGNORECASE)
_DECODING_RE = re.compile(r"\bdecoding\s*=\s*(['\"]).*?\1", re.IGNORECASE)
_PL_MONTHS = {
    1: "stycznia",
    2: "lutego",
    3: "marca",
    4: "kwietnia",
    5: "maja",
    6: "czerwca",
    7: "lipca",
    8: "sierpnia",
    9: "września",
    10: "października",
    11: "listopada",
    12: "grudnia",
}

import re
from typing import Any, Dict, List, Tuple

_H_RE = re.compile(r"<h([23])([^>]*)>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_ID_RE = re.compile(r'\bid\s*=\s*([\'"])(.*?)\1', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def slugify_id(text: str) -> str:
    # proste, stabilne id (działa z PL znakami)
    text = unescape(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # litery/cyfry -> '-', reszta out
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "sekcja"


def build_toc_and_inject_ids(html: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    - znajduje <h2> i <h3>
    - wyciąga tytuł (bez tagów)
    - nadaje/uzupełnia id (jeśli brak)
    - zwraca (nowy_html, toc_list)
    """
    if not html:
        return "", []

    toc: List[Dict[str, Any]] = []
    used: Dict[str, int] = {}

    def unique_id(base: str) -> str:
        n = used.get(base, 0)
        used[base] = n + 1
        return base if n == 0 else f"{base}-{n+1}"

    def normalize_toc_title(title: str) -> str:
        # usuń ręczne numerowanie na początku, np:
        # "1. Wstęp" -> "Wstęp"
        # "2) Coś"   -> "Coś"
        # "1.2.3. Coś" -> "Coś"
        t = title.strip()
        t2 = re.sub(r"^\s*\d+(?:\.\d+)*[.)]\s+", "", t)
        return t2 if t2 else t

    def repl(m: re.Match) -> str:
        level = int(m.group(1))
        attrs = m.group(2) or ""
        inner = m.group(3) or ""

        title_txt = _TAG_RE.sub(" ", inner)
        title_txt = re.sub(r"\s+", " ", unescape(title_txt)).strip()

        toc_title = normalize_toc_title(title_txt)

        id_match = _ID_RE.search(attrs)
        if id_match:
            hid = id_match.group(2)
        else:
            hid = unique_id(slugify_id(title_txt))
            attrs = f'{attrs} id="{hid}"'

        toc.append({"level": level, "id": hid, "title": toc_title})
        return f"<h{level}{attrs}>{inner}</h{level}>"

    new_html = _H_RE.sub(repl, html)
    return new_html, toc


WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def format_warsaw_datetime(dt_str: str) -> str:
    if not dt_str:
        return ""
    s = dt_str.replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(WARSAW_TZ)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_pl_date(date_str: str) -> str:
    """
    Wejście: ISO z PocketBase (np. '2026-02-16 12:34:56.789Z' albo '2026-02-16T...Z')
    Wyjście: '16 lutego 2026 r.'
    """
    if not date_str:
        return ""

    s = date_str.replace("Z", "+00:00").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
        return f"{dt.day} {_PL_MONTHS.get(dt.month, dt.month)} {dt.year} r."
    except Exception:
        try:
            y, m, d = (date_str[:10]).split("-")
            return f"{int(d)} {_PL_MONTHS.get(int(m), int(m))} {int(y)} r."
        except Exception:
            return date_str
COMMENT_COOLDOWN_SECONDS = 300


def pb_dt_to_utc(dt_str: str) -> datetime:
    s = (dt_str or "").replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def get_last_comment_utc_for_post(visitor_id: str, post_id: str) -> datetime | None:
    data = await pb_get(
        "/api/collections/comments/records",
        params={
            "page": 1,
            "perPage": 1,
            "sort": "-created",
            "filter": f'(visitor_id="{visitor_id}") && (post="{post_id}")',
            "fields": "created",
        },
    )
    items = data.get("items") or []
    if not items:
        return None
    return pb_dt_to_utc(items[0].get("created"))


def lazy_images(html: str) -> str:
    """
    Dodaje loading="lazy" i decoding="async" do <img>, jeśli nie ma.
    Nie rusza innych atrybutów.
    """
    if not html:
        return ""

    def repl(m: re.Match) -> str:
        attrs = m.group(1)

        if not _LOADING_RE.search(attrs):
            attrs += ' loading="lazy"'
        if not _DECODING_RE.search(attrs):
            attrs += ' decoding="async"'

        return f"<img{attrs}>"

    return _IMG_TAG_RE.sub(repl, html)


templates.env.globals["lazy_images"] = lazy_images


def calc_reading_time_minutes(html_content: str, wpm: int = 200) -> int:
    if not html_content:
        return 1

    text = _TAG_RE.sub(" ", html_content)
    text = unescape(text)
    words = re.findall(r"\S+", text)
    minutes = ceil(len(words) / max(wpm, 1))
    return max(1, minutes)


async def search_posts(query: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    q = pb_escape(query)
    flt = f'(published=true) && ((title~"{q}") || (content~"{q}"))'

    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": page,
            "perPage": per_page,
            "sort": "-created",
            "filter": flt,
        },
    )

    items = data.get("items") or []

    for it in items:
        await attach_series_data(it)

    posts = [normalize_post(it) for it in items]

    pagination = {
        "page": int(data.get("page") or page),
        "per_page": int(data.get("perPage") or per_page),
        "total_pages": int(data.get("totalPages") or 1),
        "total_items": int(data.get("totalItems") or len(posts)),
    }
    return posts, pagination


async def pb_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = PB_URL.rstrip("/") + path
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params or {})
        r.raise_for_status()
        return r.json()


def normalize_post(raw: Dict[str, Any]) -> Dict[str, Any]:
    title = raw.get("title") or ""
    slug = raw.get("slug") or ""
    content = raw.get("content") or ""
    category = raw.get("category")

    series_obj = raw.get("_series")

    if isinstance(series_obj, dict):
        suffix = (series_obj.get("suffix") or "").strip()
        description = (series_obj.get("description") or "").strip()

        if suffix:
            title = f"{title} {suffix}"

        if description:
            if content and not content.endswith("\n"):
                content += "\n"
            content += "\n<hr>\n" + description

    excerpt = (content or "").strip()
    if len(excerpt) > 240:
        excerpt = excerpt[:240].rstrip() + "…"

    created_raw = raw.get("created")
    updated_raw = raw.get("updated")

    return {
        "id": raw.get("id"),
        "title": title,
        "slug": slug,
        "meta_description": raw.get("meta_description"),
        "published": bool(raw.get("published", False)),
        "comments_on": bool(raw.get("comments_on", True)),
        "content": content,
        "excerpt": excerpt,
        "category": category,
        "creator": raw.get("creator"),
        "thumbnail": raw.get("thumbnail"),
        "thumbnail_url": pb_file_url("posts", raw.get("id"), raw.get("thumbnail")),
        "views": raw.get("views") or 0,
        "created_raw": created_raw,
        "updated_raw": updated_raw,
        "created": format_pl_date(created_raw),
        "updated": format_pl_date(updated_raw),
        "reading_time": calc_reading_time_minutes(content),
        "series": series_obj,
    }


async def get_all_posts(page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": page,
            "perPage": per_page,
            "sort": "-created",
            "filter": "published=true",
        },
    )

    items = data.get("items") or []

    for it in items:
        await attach_series_data(it)

    comment_counts = await get_comment_counts()

    posts = []
    for it in items:
        post = normalize_post(it)
        post["comments"] = comment_counts.get(post["id"], 0)
        posts.append(post)

    pagination = {
        "page": int(data.get("page") or page),
        "per_page": int(data.get("perPage") or per_page),
        "total_pages": int(data.get("totalPages") or 1),
        "total_items": int(data.get("totalItems") or len(posts)),
    }
    return posts, pagination


_SERIES_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


async def get_series_by_id(series_id: str) -> Optional[Dict[str, Any]]:
    if not series_id:
        return None

    if series_id in _SERIES_CACHE:
        return _SERIES_CACHE[series_id]

    try:
        data = await pb_get(f"/api/collections/series/records/{series_id}")
    except Exception:
        data = None

    _SERIES_CACHE[series_id] = data
    return data


async def attach_series_data(raw_post: Dict[str, Any]) -> None:
    sid = raw_post.get("series")
    if not sid:
        raw_post["_series"] = None
        return

    raw_post["_series"] = await get_series_by_id(str(sid))


import time
from typing import Optional, Dict

_COMMENT_COUNT_CACHE: Optional[Dict[str, int]] = None
_COMMENT_COUNT_CACHE_TS: float = 0.0
_COMMENT_COUNT_CACHE_TTL = 60  # sekundy

async def get_comment_counts() -> Dict[str, int]:
    global _COMMENT_COUNT_CACHE, _COMMENT_COUNT_CACHE_TS

    now = time.time()
    if _COMMENT_COUNT_CACHE is not None and (now - _COMMENT_COUNT_CACHE_TS) < _COMMENT_COUNT_CACHE_TTL:
        return _COMMENT_COUNT_CACHE

    counts: Dict[str, int] = {}
    page = 1
    per_page = 200

    while True:
        data = await pb_get(
            "/api/collections/comments/records",
            params={
                "page": page,
                "perPage": per_page,
                "filter": "approved=true",
                "fields": "post",
            },
        )

        items = data.get("items") or []
        for c in items:
            post_id = c.get("post")
            if post_id:
                counts[post_id] = counts.get(post_id, 0) + 1

        if page >= data.get("totalPages", 1):
            break
        page += 1

    _COMMENT_COUNT_CACHE = counts
    _COMMENT_COUNT_CACHE_TS = now
    return counts


def build_pagination_context(request: Request, pagination: Dict[str, Any]) -> Dict[str, Any]:
    page = int(pagination["page"])
    total_pages = int(pagination["total_pages"])

    def url_for(p: int) -> str:
        return str(request.url.remove_query_params("page").include_query_params(page=p))

    prev_url = url_for(page - 1) if page > 1 else None
    next_url = url_for(page + 1) if page < total_pages else None

    page_urls = {p: url_for(p) for p in range(1, total_pages + 1)}

    return {
        "page": page,
        "total_pages": total_pages,
        "prev_url": prev_url,
        "next_url": next_url,
        "page_urls": page_urls,
    }


def build_pagination_html(request: Request, pagination: Dict[str, Any]) -> str:
    page = int(pagination["page"])
    total = int(pagination["total_pages"])
    if total <= 1:
        return ""

    def url_for(p: int) -> str:
        return str(request.url.remove_query_params("page").include_query_params(page=p))

    parts = ['<div class="pagination">']

    if page > 1:
        parts.append(f'<a href="{url_for(page-1)}">« Poprzednia</a>')

    for p in range(1, total + 1):
        if p == page:
            parts.append(f"<strong>{p}</strong>")
        else:
            parts.append(f'<a href="{url_for(p)}">{p}</a>')

    if page < total:
        parts.append(f'<a href="{url_for(page+1)}">Następna »</a>')

    parts.append("</div>")
    return "".join(parts)


async def get_categories() -> List[str]:
    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": 1,
            "perPage": 200,
            "filter": "published=true",
            "fields": "category",
        },
    )
    cats: List[str] = []
    for it in (data.get("items") or []):
        c = it.get("category")
        if c and c not in cats:
            cats.append(c)
    return sorted(cats)


async def get_top_posts(limit: int = 5) -> List[Dict[str, Any]]:
    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": 1,
            "perPage": limit,
            "sort": "-views",
            "filter": "published=true",
            "expand": "series",
        },
    )
    return [normalize_post(it) for it in (data.get("items") or [])]


async def get_top_commented(limit: int = 5) -> List[Dict[str, Any]]:
    counts = await get_comment_counts()

    if not counts:
        return []

    top_pairs = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_ids = [pid for pid, _ in top_pairs]

    or_part = " || ".join([f'id="{pid}"' for pid in top_ids])
    flt = f'(published=true) && (comments_on=true) && ({or_part})'

    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": 1,
            "perPage": limit,
            "filter": flt,
        },
    )

    items = data.get("items") or []

    for it in items:
        await attach_series_data(it)

    posts = [normalize_post(it) for it in items]

    by_id = {p["id"]: p for p in posts}
    result: List[Dict[str, Any]] = []
    for pid, cnt in top_pairs:
        p = by_id.get(pid)
        if not p:
            continue
        p["comments"] = int(cnt)
        result.append(p)

    return result


async def get_post_count() -> int:
    data = await pb_get(
        "/api/collections/posts/records",
        params={"page": 1, "perPage": 1, "filter": "published=true", "fields": "id"},
    )
    return int(data.get("totalItems") or 0)


from fastapi import HTTPException


async def get_posts_by_category(category: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cat = pb_escape(category)

    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": page,
            "perPage": per_page,
            "sort": "-created",
            "filter": f'(published=true) && (category="{cat}")',
        },
    )

    items = data.get("items") or []
    for it in items:
        await attach_series_data(it)

    posts = [normalize_post(it) for it in items]

    pagination = {
        "page": int(data.get("page") or page),
        "per_page": int(data.get("perPage") or per_page),
        "total_pages": int(data.get("totalPages") or 1),
        "total_items": int(data.get("totalItems") or len(posts)),
    }
    return posts, pagination


async def public_context(request: Request) -> Dict[str, Any]:
    return {
        "query": request.query_params.get("q"),
        "selected_category": request.query_params.get("category"),
        "categories": await get_categories(),
        "top_posts": await get_top_posts(limit=5),
        "top_commented": await get_top_commented(limit=5),
        "post_count": await get_post_count(),
    }


async def render_template(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    base = await public_context(request)
    merged = {**base, **ctx}
    return templates.TemplateResponse(name, {"request": request, **merged})


from fastapi import HTTPException, Query


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    page: int = Query(1),
    per_page: int = Query(10, ge=1, le=50),
):
    if page < 1:
        raise HTTPException(status_code=404)

    posts, pagination = await get_all_posts(page=page, per_page=per_page)

    total_pages = int(pagination["total_pages"])
    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404)

    pagination_html = build_pagination_html(request, pagination)
    pag_ctx = build_pagination_context(request, pagination)

    return await render_template(
        request,
        "index.html",
        posts=posts,
        pagination=pagination,
        pagination_html=pagination_html,
        **pag_ctx,
        context_name=None,
    )


@router.get("/moje-projekty", response_class=HTMLResponse)
async def moje_projekty(request: Request):
    return await render_template(request, "moje-projekty.html", context_name="moje-projekty")


@router.get("/o-blogu", response_class=HTMLResponse)
async def o_blogu(request: Request):
    return await render_template(request, "o-blogu.html", context_name="o-blogu")


@router.get("/o-mnie", response_class=HTMLResponse)
async def o_mnie(request: Request):
    return await render_template(request, "o-mnie.html", context_name="o-mnie")


@router.get("/warunki", response_class=HTMLResponse)
async def warunki(request: Request):
    return await render_template(request, "warunki.html", context_name="warunki")


@router.get("/polityka-prywatnosci", response_class=HTMLResponse)
async def polityka_prywatnosci(request: Request):
    return await render_template(request, "polityka-prywatnosci.html", context_name="polityka-prywatnosci")


from datetime import datetime
from fastapi import HTTPException


def pb_file_url(collection: str, record_id: str, filename: Optional[str]) -> Optional[str]:
    if not record_id or not filename:
        return None
    return f"{PB_URL.rstrip('/')}/api/files/{collection}/{record_id}/{filename}"


COMMENT_COOLDOWN_SECONDS = 300


def pb_dt_to_utc(dt_str: str) -> datetime:
    s = (dt_str or "").replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def get_last_comment_utc(visitor_id: str) -> datetime | None:
    data = await pb_get(
        "/api/collections/comments/records",
        params={
            "page": 1,
            "perPage": 1,
            "sort": "-created",
            "filter": f'visitor_id="{visitor_id}"',
            "fields": "created",
        },
    )
    items = data.get("items") or []
    if not items:
        return None
    return pb_dt_to_utc(items[0].get("created"))


def normalize_comment(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "post": raw.get("post"),
        "visitor_id": raw.get("visitor_id"),
        "author": raw.get("author") or "",
        "email": raw.get("email") or "",
        "content": raw.get("content") or "",
        "approved": bool(raw.get("approved", False)),
        "created": raw.get("created"),
        "updated": raw.get("updated"),
        "created_pl": format_warsaw_datetime(raw.get("created")),
    }


async def get_post_by_slug(slug: str) -> Dict[str, Any]:
    data = await pb_get(
        "/api/collections/posts/records",
        params={
            "page": 1,
            "perPage": 1,
            "filter": f'(published=true) && (slug="{slug}")',
        },
    )
    items = data.get("items") or []
    if not items:
        raise HTTPException(status_code=404, detail="Post not found")

    raw = items[0]
    await attach_series_data(raw)

    post = normalize_post(raw)

    post["content"], post["toc"] = build_toc_and_inject_ids(post.get("content", ""))

    if post.get("comments_on"):
        post["toc"].append({"level": 2, "id": "comments", "title": "Komentarze"})

    comment_counts = await get_comment_counts()
    post["comments"] = comment_counts.get(post["id"], 0)

    post["thumbnail"] = post["thumbnail_url"]
    post["seo_date"] = post.get("created_raw") or ""

    return post


async def pb_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = PB_URL.rstrip("/") + path
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


async def get_comments_for_post(post_id: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = await pb_get(
        "/api/collections/comments/records",
        params={
            "page": page,
            "perPage": per_page,
            "sort": "-created",
            "filter": f'(post="{post_id}") && (approved=true)',
        },
    )

    items = data.get("items") or []
    comments = [normalize_comment(it) for it in items]

    meta = {
        "page": int(data.get("page") or page),
        "per_page": int(data.get("perPage") or per_page),
        "total_pages": int(data.get("totalPages") or 1),
        "total_items": int(data.get("totalItems") or len(comments)),
    }
    return comments, meta


@router.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(
    request: Request,
    slug: str,
    cpage: int = Query(1, ge=1),
):
    post = await get_post_by_slug(slug)

    comments, cmeta = await get_comments_for_post(post["id"], page=cpage, per_page=10)

    prefill_author = request.cookies.get("comment_author", "")
    prefill_email = request.cookies.get("comment_email", "")

    return await render_template(
        request,
        "post.html",
        post=post,
        comments=comments,
        comments_page=cmeta["page"],
        comments_total_pages=cmeta["total_pages"],
        comments_total_items=cmeta["total_items"],
        active_reaction=None,
        prefill_author=prefill_author,
        prefill_email=prefill_email,
        recaptcha_site_key=RECAPTCHA_SITE_KEY,
        context_name="post",
    )


@router.post("/post/{slug}/comment")
async def add_comment(
    request: Request,
    slug: str,
    author: str = Form(...),
    content: str = Form(...),
    email: str = Form(""),
    terms_accepted: str = Form(None),
    recaptcha_response: str = Form(None, alias="g-recaptcha-response"),  # ✅
):
    post = await get_post_by_slug(slug)
    if not post.get("comments_on", True):
        raise HTTPException(status_code=404)

    author = (author or "").strip()
    email = (email or "").strip()
    content = (content or "").strip()

    if not author or len(author) > 20:
        raise HTTPException(status_code=400, detail="Nieprawidłowe imię")
    if len(email) > 30:
        raise HTTPException(status_code=400, detail="Nieprawidłowy email")
    if not content or len(content) > 200:
        raise HTTPException(status_code=400, detail="Nieprawidłowa treść komentarza")
    if terms_accepted is None:
        raise HTTPException(status_code=400, detail="Musisz zaakceptować warunki")

    # ✅ CAPTCHA (toast zrobi scripts.js)
    ok = await verify_recaptcha(
        token=recaptcha_response or "",
        remoteip=request.client.host if request.client else None,
    )
    if not ok:
        return RedirectResponse(url=f"/post/{slug}?captcha=1#comments", status_code=303)

    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = secrets.token_hex(16)

    # ✅ cooldown tylko gdy za szybko
    last_dt = await get_last_comment_utc_for_post(visitor_id, post["id"])
    if last_dt:
        now_utc = datetime.now(timezone.utc)
        elapsed = (now_utc - last_dt).total_seconds()
        remaining = int(COMMENT_COOLDOWN_SECONDS - elapsed)
        if remaining > 0:
            resp = RedirectResponse(url=f"/post/{slug}?cooldown={remaining}#comments", status_code=303)
            if "visitor_id" not in request.cookies:
                resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
            return resp

    await pb_post(
        "/api/collections/comments/records",
        payload={
            "post": post["id"],
            "visitor_id": visitor_id,
            "author": author,
            "email": email,
            "content": content,
            "approved": True,
        },
    )

    global _COMMENT_COUNT_CACHE
    _COMMENT_COUNT_CACHE = None

    # ✅ sukces: tylko sent=1 (bez cooldown)
    resp = RedirectResponse(url=f"/post/{slug}?sent=1#comments", status_code=303)
    if "visitor_id" not in request.cookies:
        resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp


from fastapi import HTTPException


@router.get("/szukaj", response_class=HTMLResponse)
async def search_view(
    request: Request,
    q: str = Query("", alias="q"),
    page: int = Query(1),
    per_page: int = Query(10, ge=1, le=50),
):
    query = (q or "").strip()

    if page < 1:
        raise HTTPException(status_code=404)

    if not query:
        return await render_template(
            request,
            "szukaj.html",
            query="",
            posts=[],
            page=1,
            total_pages=1,
            pagination_html="",
            context_name="search",
        )

    posts, pagination = await search_posts(query=query, page=page, per_page=per_page)

    total_pages = int(pagination["total_pages"])
    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404)

    pagination_html = build_pagination_html(request, pagination)
    pag_ctx = build_pagination_context(request, pagination)

    return await render_template(
        request,
        "szukaj.html",
        query=query,
        posts=posts,
        pagination=pagination,
        pagination_html=pagination_html,
        **pag_ctx,
        context_name="search",
    )


@router.get("/kategorie/{category}", response_class=HTMLResponse)
async def category_view(
    request: Request,
    category: str,
    page: int = Query(1),
    per_page: int = Query(10, ge=1, le=50),
):
    if page < 1:
        raise HTTPException(status_code=404)

    posts, pagination = await get_posts_by_category(category=category, page=page, per_page=per_page)

    total_pages = int(pagination["total_pages"])
    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404)

    pagination_html = build_pagination_html(request, pagination)
    pag_ctx = build_pagination_context(request, pagination)

    return await render_template(
        request,
        "kategorie.html",
        posts=posts,
        query="",
        context_name=category,
        selected_category=category,
        pagination=pagination,
        pagination_html=pagination_html,
        **pag_ctx,
    )
def _clean_header(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").strip()


async def verify_recaptcha(token: str, remoteip: str | None = None) -> bool:
    if not token:
        return False

    payload = {"secret": RECAPTCHA_SECRET_KEY, "response": token}
    if remoteip:
        payload["remoteip"] = remoteip

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post("https://www.google.com/recaptcha/api/siteverify", data=payload)
        data = r.json()
        return bool(data.get("success"))


def send_contact_email_sync(name: str, email: str, subject: str, message: str, vid: str | None) -> None:
    msg = EmailMessage()
    msg["From"] = CONTACT_FROM
    msg["To"] = CONTACT_TO
    msg["Subject"] = _clean_header(f"[Kontakt] {subject}")
    msg["Reply-To"] = _clean_header(email)

    body = (
        "Nowa wiadomość z formularza kontaktowego:\n\n"
        f"Imię: {name}\n"
        f"E-mail: {email}\n"
        f"Temat: {subject}\n"
        f"VID: {vid or '(brak)'}\n\n"
        "Wiadomość:\n"
        f"{message}\n"
    )

    msg.set_content(body)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
CONTACT_COOLDOWN_SECONDS = 600  # 10 minut


def _now_utc_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _parse_int(s: str | None) -> int | None:
    try:
        return int(s) if s is not None else None
    except Exception:
        return None


@router.get("/kontakt", response_class=HTMLResponse)
async def kontakt(request: Request):
    # ✅ brak sent/error w HTML — toast obsłuży JS po query paramach
    return await render_template(
        request,
        "kontakt.html",
        context_name="kontakt",
        recaptcha_site_key=RECAPTCHA_SITE_KEY,
    )


@router.post("/post/{slug}/comment")
async def add_comment(
    request: Request,
    slug: str,
    author: str = Form(...),
    content: str = Form(...),
    email: str = Form(""),
    terms_accepted: str = Form(None),
    recaptcha_response: str = Form(None, alias="g-recaptcha-response"),  # <-- DODAJ TO
):
    post = await get_post_by_slug(slug)
    if not post.get("comments_on", True):
        raise HTTPException(status_code=404)

    author = (author or "").strip()
    email = (email or "").strip()
    content = (content or "").strip()

    if not author or len(author) > 20:
        raise HTTPException(status_code=400, detail="Nieprawidłowe imię")
    if len(email) > 30:
        raise HTTPException(status_code=400, detail="Nieprawidłowy email")
    if not content or len(content) > 200:
        raise HTTPException(status_code=400, detail="Nieprawidłowa treść komentarza")
    if terms_accepted is None:
        raise HTTPException(status_code=400, detail="Musisz zaakceptować warunki")

    # ✅ CAPTCHA: jeśli niezaznaczona albo nie przeszła, pokaż toast przez scripts.js
    ok = await verify_recaptcha(
        token=recaptcha_response or "",
        remoteip=request.client.host if request.client else None,
    )
    if not ok:
        return RedirectResponse(url=f"/post/{slug}?captcha=1#comments", status_code=303)

    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = secrets.token_hex(16)

    # ✅ cooldown tylko przy próbie "za szybko"
    last_dt = await get_last_comment_utc_for_post(visitor_id, post["id"])
    if last_dt:
        now_utc = datetime.now(timezone.utc)
        elapsed = (now_utc - last_dt).total_seconds()
        remaining = int(COMMENT_COOLDOWN_SECONDS - elapsed)
        if remaining > 0:
            resp = RedirectResponse(
                url=f"/post/{slug}?cooldown={remaining}#comments",
                status_code=303,
            )
            if "visitor_id" not in request.cookies:
                resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
            return resp

    await pb_post(
        "/api/collections/comments/records",
        payload={
            "post": post["id"],
            "visitor_id": visitor_id,
            "author": author,
            "email": email,
            "content": content,
            "approved": True,
        },
    )

    global _COMMENT_COUNT_CACHE
    _COMMENT_COUNT_CACHE = None

    resp = RedirectResponse(url=f"/post/{slug}?sent=1#comments", status_code=303)
    if "visitor_id" not in request.cookies:
        resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp


app.include_router(router)
