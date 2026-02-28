from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, FastAPI, HTTPException, Request, status, Query, Form, Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.parse import quote_plus
from html import unescape
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from bs4 import BeautifulSoup
import httpx
import uuid
import unicodedata
import smtplib
import asyncio
import time
import secrets
import re
import time
from app.config import (
    PB_URL,
    POSTS_COLLECTION,
    COMMENTS_COLLECTION,
    SERIES_COLLECTION,
    SERVICE_COLLECTION,
    RECAPTCHA_SITE_KEY,
    RECAPTCHA_SECRET_KEY,
    PB_SERVICE_EMAIL,
    PB_SERVICE_PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    CONTACT_TO,
    CONTACT_FROM,
)

# --- HTTP client reuse (one AsyncClient per process) ---
_HTTP_CLIENT: httpx.AsyncClient | None = None

async def get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=15)
    return _HTTP_CLIENT

async def close_http_client() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None

app = FastAPI()

@app.on_event("startup")
async def startup_http_client() -> None:
    await get_http_client()

@app.on_event("shutdown")
async def shutdown_http_client() -> None:
    await close_http_client()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.state.templates = templates
templates.env.filters["urlencode"] = lambda s: quote_plus(str(s))

router = APIRouter()

_SERVICE_TOKEN: str | None = None
_SERVICE_TOKEN_TS: float = 0.0
_SERVICE_TOKEN_TTL = 60 * 30  # 30 min (prosto; potem można lepiej)

VISITOR_COOKIE_NAME = "visitor_id"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 rok

WARSAW_TZ = ZoneInfo("Europe/Warsaw")

COMMENT_COOLDOWN_SECONDS = 300

@app.middleware("http")
async def ensure_visitor_id_cookie(request: Request, call_next):
    response = await call_next(request)

    # jeśli już jest, nic nie rób
    if request.cookies.get(VISITOR_COOKIE_NAME):
        return response

    # ustaw cookie tylko gdy response jeszcze nie ma Set-Cookie dla visitor_id
    # (zabezpiecza przed podwójnym ustawieniem w np. add_comment)
    new_vid = secrets.token_hex(16)
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        new_vid,
        max_age=VISITOR_COOKIE_MAX_AGE,
        samesite="lax",
        httponly=True,
    )
    return response

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

async def pb_login_service() -> str:
    if not PB_SERVICE_EMAIL or not PB_SERVICE_PASSWORD:
        raise RuntimeError("Missing PB_SERVICE_EMAIL / PB_SERVICE_PASSWORD")

    data = await pb_post_noauth(
        f"/api/collections/{SERVICE_COLLECTION}/auth-with-password",
        {"identity": PB_SERVICE_EMAIL, "password": PB_SERVICE_PASSWORD},
    )

    token = data.get("token")
    if not token:
        raise RuntimeError("PocketBase login did not return token")
    return token

async def get_service_token() -> str:
    global _SERVICE_TOKEN, _SERVICE_TOKEN_TS
    now = time.time()

    if _SERVICE_TOKEN and (now - _SERVICE_TOKEN_TS) < _SERVICE_TOKEN_TTL:
        return _SERVICE_TOKEN

    token = await pb_login_service()
    _SERVICE_TOKEN = token
    _SERVICE_TOKEN_TS = now
    return token

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

async def get_last_comment_utc_for_post(visitor_id: str, post_id: str) -> datetime | None:
    data = await pb_get(
        f"/api/collections/{COMMENTS_COLLECTION}/records",
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

def build_gallery_html(gallery_items: list[dict]) -> str:
    # gallery_items: [{"url": "...", "thumb": "...", "alt": "..."}]
    parts = ['<div class="gallery-grid">']
    for it in gallery_items:
        parts.append(
            f'<a href="{it["url"]}" class="gallery-item" data-full="{it["url"]}">'
            f'  <img src="{it["thumb"]}" alt="{it.get("alt","")}" loading="lazy">'
            f'</a>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def inject_gallery_placeholders(post_html: str, gallery_items: list[dict]) -> str:
    if not post_html or not gallery_items:
        return post_html

    soup = BeautifulSoup(post_html, "html.parser")

    # wszystkie <section class="gallery">...</section>
    for sec in soup.select("section.gallery"):
        # opcjonalnie: jeśli chcesz tylko puste sekcje
        # if sec.get_text(strip=True): continue

        sec.clear()
        sec.append(BeautifulSoup(build_gallery_html(gallery_items), "html.parser"))

    return str(soup)

def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        # gdybyś kiedyś trzymał tagi jako CSV
        return [x.strip() for x in v.split(",") if x.strip()]
    return []

def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # PocketBase zwykle daje ISO, czasem z 'Z'
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

async def get_related_posts(post: dict, limit: int = 6) -> list[dict]:
    """
    Automatycznie dobiera podobne posty:
    - mocno promuje tę samą kategorię
    - promuje wspólne tagi
    - lekko promuje popularność (views) i świeżość (created)
    """
    post_id = post.get("id")
    slug = post.get("slug")
    category = (post.get("category") or "").strip()
    tags = set(_as_list(post.get("tags")))

    # 1) pobierz kandydatów z tej samej kategorii (dużo jakości za mało zapytań)
    candidates = []
    if category:
        data = await pb_get(
            f"/api/collections/{POSTS_COLLECTION}/records",
            params={
                "page": 1,
                "perPage": 80,  # wystarczy na ranking
                "filter": f'published=true && category="{category}" && id!="{post_id}"',
                "fields": "id,slug,title,category,tags,views,created",
                "sort": "-views,-created",
            },
        )
        candidates = data.get("items") or []

    # 2) jeśli mało, dobierz z “reszty świata” (fallback)
    if len(candidates) < limit:
        data2 = await pb_get(
            f"/api/collections/{POSTS_COLLECTION}/records",
            params={
                "page": 1,
                "perPage": 120,
                "filter": f'published=true && id!="{post_id}"',
                "fields": "id,slug,title,category,tags,views,created",
                "sort": "-views,-created",
            },
        )
        more = data2.get("items") or []
        # doklej bez duplikatów
        seen = {c.get("id") for c in candidates}
        for it in more:
            if it.get("id") not in seen:
                candidates.append(it)
                seen.add(it.get("id"))
            if len(candidates) >= 200:
                break

    # 3) scoring
    now = datetime.now(timezone.utc)

    def score(p: dict) -> float:
        s = 0.0

        # kategoria
        if category and (p.get("category") or "").strip() == category:
            s += 100.0

        # tagi wspólne
        ptags = set(_as_list(p.get("tags")))
        common = len(tags & ptags) if tags else 0
        s += common * 15.0

        # popularność
        try:
            s += min(float(p.get("views") or 0), 1000.0) * 0.02  # do +20 pkt
        except Exception:
            pass

        # świeżość (delikatnie)
        dt = _parse_dt(p.get("created"))
        if dt:
            days = max((now - dt).days, 0)
            s += max(0.0, 20.0 - min(days, 400) * 0.05)  # do +20, spada powoli

        return s

    candidates.sort(key=score, reverse=True)
    return candidates[:limit]

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
        f"/api/collections/{POSTS_COLLECTION}/records",
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
    token = await get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    client = await get_http_client()
    r = await client.get(url, params=params or {}, headers=headers)
    r.raise_for_status()
    return r.json()

async def pb_patch(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = PB_URL.rstrip("/") + path
    token = await get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    client = await get_http_client()
    r = await client.patch(url, json=payload, headers=headers)
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
        "thumbnail_url": pb_file_url(f"{POSTS_COLLECTION}", raw.get("id"), raw.get("thumbnail")),
        "views": raw.get("views") or 0,
        "created_raw": created_raw,
        "updated_raw": updated_raw,
        "created": format_pl_date(created_raw),
        "updated": format_pl_date(updated_raw),
        "reading_time": calc_reading_time_minutes(content),
        "series": series_obj,
        "sources": raw.get("sources") or [],
        "tags": raw.get("tags") or [],
    }


async def get_all_posts(page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = await pb_get(
        f"/api/collections/{POSTS_COLLECTION}/records",
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
        data = await pb_get(f"/api/collections/{SERIES_COLLECTION}/records/{series_id}")
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

_PUBLIC_CACHE: dict[str, tuple[float, Any]] = {}

def _cache_get(key: str, ttl: int) -> Any | None:
    now = time.time()
    hit = _PUBLIC_CACHE.get(key)
    if not hit:
        return None
    ts, val = hit
    if (now - ts) < ttl:
        return val
    return None

def _cache_set(key: str, val: Any) -> Any:
    _PUBLIC_CACHE[key] = (time.time(), val)
    return val

def _cache_invalidate(prefix: str) -> None:
    # usuwa wszystkie klucze zaczynające się od prefix
    for k in list(_PUBLIC_CACHE.keys()):
        if k.startswith(prefix):
            _PUBLIC_CACHE.pop(k, None)

async def get_public_widgets_cached() -> Dict[str, Any]:
    # TTL-e (sekundy) – dobrane pod bloga
    TTL_CATEGORIES = 60 * 30      # 30 min
    TTL_TOP_POSTS = 60 * 2        # 2 min
    TTL_TOP_COMMENTED = 60 * 2    # 2 min
    TTL_POST_COUNT = 60 * 5       # 5 min

    categories = _cache_get("public:categories", TTL_CATEGORIES)
    if categories is None:
        categories = _cache_set("public:categories", await get_categories())

    top_posts = _cache_get("public:top_posts", TTL_TOP_POSTS)
    if top_posts is None:
        top_posts = _cache_set("public:top_posts", await get_top_posts(limit=5))

    top_commented = _cache_get("public:top_commented", TTL_TOP_COMMENTED)
    if top_commented is None:
        top_commented = _cache_set("public:top_commented", await get_top_commented(limit=5))

    post_count = _cache_get("public:post_count", TTL_POST_COUNT)
    if post_count is None:
        post_count = _cache_set("public:post_count", await get_post_count())

    return {
        "categories": categories,
        "top_posts": top_posts,
        "top_commented": top_commented,
        "post_count": post_count,
    }

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
            f"/api/collections/{COMMENTS_COLLECTION}/records",
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
        f"/api/collections/{POSTS_COLLECTION}/records",
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
        f"/api/collections/{POSTS_COLLECTION}/records",
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
        f"/api/collections/{POSTS_COLLECTION}/records",
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
        f"/api/collections/{POSTS_COLLECTION}/records",
        params={"page": 1, "perPage": 1, "filter": "published=true", "fields": "id"},
    )
    return int(data.get("totalItems") or 0)

async def get_posts_by_category(category: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cat = pb_escape(category)

    data = await pb_get(
        f"/api/collections/{POSTS_COLLECTION}/records",
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
    try:
        widgets = await get_public_widgets_cached()
    except Exception as e:
        print("[WIDGETS ERROR]", repr(e))
        widgets = {"categories": [], "top_posts": [], "top_commented": [], "post_count": 0}

    return {
        "query": request.query_params.get("q"),
        "selected_category": request.query_params.get("category"),
        **widgets,
    }

async def render_template(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    base = await public_context(request)
    merged = {**base, **ctx}
    return templates.TemplateResponse(name, {"request": request, **merged})

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

def pb_file_url(collection: str, record_id: str, filename: Optional[str]) -> Optional[str]:
    if not record_id or not filename:
        return None
    return f"{PB_URL.rstrip('/')}/api/files/{collection}/{record_id}/{filename}"

def pb_dt_to_utc(dt_str: str) -> datetime:
    s = (dt_str or "").replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

async def get_last_comment_utc(visitor_id: str) -> datetime | None:
    data = await pb_get(
        f"/api/collections/{COMMENTS_COLLECTION}/records",
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
        f"/api/collections/{POSTS_COLLECTION}/records",
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

    # =========================
    # ✅ GALERIA: z pola PB "gallery" + placeholder w HTML
    # W treści posta wklejasz: <section class="gallery"></section>
    # =========================

    def _gallery_items_from_post(raw_post: Dict[str, Any]) -> List[Dict[str, str]]:
        files = raw_post.get("gallery") or []
        rid = raw_post.get("id")
        out: List[Dict[str, str]] = []
        for fn in files:
            if not fn:
                continue
            url = pb_file_url(f"{POSTS_COLLECTION}", rid, fn)
            thumb = url + "?thumb=500x0"  # możesz zmienić rozmiar
            out.append({"url": url, "thumb": thumb, "alt": fn})
        return out

    def _build_gallery_html(items: List[Dict[str, str]]) -> str:
        if not items:
            return ""
        parts = ['<div class="gallery-grid">']
        for it in items:
            parts.append(
                f'<a href="{it["url"]}" class="gallery-item" data-full="{it["url"]}">'
                f'<img src="{it["thumb"]}" alt="{it.get("alt","")}" loading="lazy" decoding="async">'
                f"</a>"
            )
        parts.append("</div>")
        return "".join(parts)

    def _inject_gallery_placeholder(html: str, gallery_html: str) -> str:
        if not html or not gallery_html:
            return html or ""
        # Najprostszy i stabilny wariant: dokładny placeholder
        placeholder = '<section class="gallery"></section>'
        if placeholder in html:
            return html.replace(placeholder, f'<section class="gallery">{gallery_html}</section>')
        # Minimalny fallback na whitespace/newline z edytora
        placeholder2 = '<section class="gallery"> </section>'
        if placeholder2 in html:
            return html.replace(placeholder2, f'<section class="gallery">{gallery_html}</section>')
        return html

    post["gallery_items"] = _gallery_items_from_post(raw)
    post["content"] = _inject_gallery_placeholder(post.get("content", ""), _build_gallery_html(post["gallery_items"]))

    # TOC + id w nagłówkach
    post["content"], post["toc"] = build_toc_and_inject_ids(post.get("content", ""))

    if post.get("comments_on"):
        post["toc"].append({"level": 2, "id": "comments", "title": "Komentarze"})

    comment_counts = await get_comment_counts()
    post["comments"] = comment_counts.get(post["id"], 0)

    post["thumbnail"] = post["thumbnail_url"]
    post["seo_date"] = post.get("created_raw") or ""

    post["related_posts"] = await get_related_posts(post, limit=6)

    return post

async def pb_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = PB_URL.rstrip("/") + path
    token = await get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    client = await get_http_client()
    r = await client.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

async def pb_post_noauth(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = PB_URL.rstrip("/") + path
    client = await get_http_client()
    r = await client.post(url, json=payload)
    r.raise_for_status()
    return r.json()

async def get_comments_for_post(post_id: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = await pb_get(
        f"/api/collections/{COMMENTS_COLLECTION}/records",
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

# --- views: próbujemy utworzyć rekord 1/visitor/post/day (day = początek dnia UTC) ---
    visitor_id = request.cookies.get(VISITOR_COOKIE_NAME)
    if visitor_id:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            await pb_post(
                "/api/collections/views/records",
                {
                    "visitor_id": visitor_id,
                    "post": post["id"],
                    "day": day_start.isoformat(),
                },
            )
            print(f"[VIEW] created views record post={post['id']} slug={slug} visitor={visitor_id[:6]}… day={day_start.date()}")
        except httpx.HTTPStatusError as exc:
            # Przy UNIQUE INDEX (visitor_id, post, day) -> duplikat = ignorujemy
            status_code = exc.response.status_code
            body = ""
            try:
                body = exc.response.text or ""
            except Exception:
                body = ""

            low = body.lower()
            is_duplicate = status_code in (400, 409) and ("unique" in low or "constraint" in low or "already exists" in low)

            if is_duplicate:
                print(f"[VIEW] duplicate (ignored) post={post['id']} slug={slug} visitor={visitor_id[:6]}… day={day_start.date()}")
            else:
                print(f"[VIEW] ERROR status={status_code} post={post['id']} slug={slug} body={body[:200]!r}")

    comments, cmeta = await get_comments_for_post(post["id"], page=cpage, per_page=10)

    qp = request.query_params
    prefill_author = (qp.get("ca") or request.cookies.get("comment_author", "")).strip()
    prefill_email = (qp.get("ce") or request.cookies.get("comment_email", "")).strip()
    prefill_content = (qp.get("cc") or "").strip()

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
        prefill_content=prefill_content,
        recaptcha_site_key=RECAPTCHA_SITE_KEY,
        context_name="post",
    )

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
            query="",              # do tekstu "wyniki dla"
            query_input="",        # do value w input
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
        query=query,            # do wyświetlenia na stronie
        query_input="",         # input zawsze pusty
        posts=posts,
        pagination=pagination,
        pagination_html=pagination_html,
        **pag_ctx,
        context_name="search",
    )

@app.get("/tag/{tag}", response_class=HTMLResponse)
async def tag_page(
    request: Request,
    tag: str,
    page: int = Query(1),
    per_page: int = Query(10, ge=1, le=50),
):
    if page < 1:
        raise HTTPException(status_code=404)

    # filtr dla multi-select tags
    filter_str = f'published=true && tags ~ "{tag}"'

    data = await pb_get(
        f"/api/collections/{POSTS_COLLECTION}/records",
        params={
            "page": page,
            "perPage": per_page,
            "filter": filter_str,
            "sort": "-created",
        },
    )

    items = data.get("items") or []
    posts = [normalize_post(it) for it in items]

    total_pages = int(data.get("totalPages") or 1)
    if total_pages > 0 and page > total_pages:
        raise HTTPException(status_code=404)

    pagination_html = build_pagination_html(request, {
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_items": data.get("totalItems", 0),
    })
    pag_ctx = build_pagination_context(request, {
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_items": data.get("totalItems", 0),
    })

    return await render_template(
        request,
        "tag.html",
        posts=posts,
        selected_tag=tag,
        pagination_html=pagination_html,
        pagination={
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": data.get("totalItems", 0),
        },
        **pag_ctx,
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
# visitor_id -> last_sent_ts
_CONTACT_LAST: Dict[str, int] = {}

def _now_utc_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _parse_int(s: str | None) -> int | None:
    try:
        return int(s) if s is not None else None
    except Exception:
        return None


@router.get("/kontakt", response_class=HTMLResponse)
async def kontakt(request: Request):
    qp = request.query_params

    prefill_name = (qp.get("cn") or "").strip()
    prefill_email = (qp.get("ce") or "").strip()
    prefill_message = (qp.get("cm") or "").strip()

    return await render_template(
        request,
        "kontakt.html",
        context_name="kontakt",
        recaptcha_site_key=RECAPTCHA_SITE_KEY,
        prefill_name=prefill_name,
        prefill_email=prefill_email,
        prefill_message=prefill_message,
    )


@router.post("/kontakt")
async def kontakt_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    recaptcha_response: str = Form(None, alias="g-recaptcha-response"),
):
    def _prefill_redirect(error_code: str) -> RedirectResponse:
        qs = urlencode(
            {
                "error": error_code,
                "cn": (name or "")[:40],
                "ce": (email or "")[:80],
                "cs": (subject or "")[:120],
                "cm": (message or "")[:1000],
            }
        )
        return RedirectResponse(url=f"/kontakt?{qs}#kontakt", status_code=303)

    # VID z middleware cookie
    vid = request.cookies.get("visitor_id")
    now = _now_utc_ts()

    # prościutki cooldown per visitor
    if vid:
        last = _CONTACT_LAST.get(vid)
        if last is not None and (now - last) < CONTACT_COOLDOWN_SECONDS:
            return _prefill_redirect("cooldown")

    # reCAPTCHA
    ok = await verify_recaptcha(
        recaptcha_response,
        remoteip=request.client.host if request.client else None,
    )
    if not ok:
        return _prefill_redirect("recaptcha")

    # wysyłka maila (SMTP jest sync, więc do wątku)
    try:
        await asyncio.to_thread(send_contact_email_sync, name, email, subject, message, vid)
    except Exception as e:
        print("[CONTACT ERROR]", repr(e))
        return _prefill_redirect("send")

    if vid:
        _CONTACT_LAST[vid] = now

    return RedirectResponse(url="/kontakt?sent=1#kontakt", status_code=303)


@router.post("/post/{slug}/comment")
async def add_comment(
    request: Request,
    slug: str,
    author: str = Form(...),
    content: str = Form(...),
    email: str = Form(""),
    terms_accepted: str = Form(None),
    recaptcha_response: str = Form(None, alias="g-recaptcha-response"),
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

    # helper do redirectów z prefill
    def _prefill_redirect(error_code: str, extra: dict | None = None) -> RedirectResponse:
        params = {
            "error": error_code,
            "ca": author[:20],
            "ce": email[:30],
            "cc": content[:200],
        }
        if extra:
            params.update(extra)
        qs = urlencode(params)
        return RedirectResponse(url=f"/post/{slug}?{qs}#comments", status_code=303)

    # ✅ CAPTCHA
    ok = await verify_recaptcha(
        token=recaptcha_response or "",
        remoteip=request.client.host if request.client else None,
    )
    if not ok:
        return _prefill_redirect("recaptcha")

    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = secrets.token_hex(16)

    # ✅ cooldown
    last_dt = await get_last_comment_utc_for_post(visitor_id, post["id"])
    if last_dt:
        now_utc = datetime.now(timezone.utc)
        elapsed = (now_utc - last_dt).total_seconds()
        remaining = int(COMMENT_COOLDOWN_SECONDS - elapsed)
        if remaining > 0:
            resp = _prefill_redirect("cooldown", {"t": str(remaining)})
            if "visitor_id" not in request.cookies:
                resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
            return resp

    await pb_post(
        f"/api/collections/{COMMENTS_COLLECTION}/records",
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
    _cache_invalidate("public:")


    resp = RedirectResponse(url=f"/post/{slug}?sent=1#comments", status_code=303)
    if "visitor_id" not in request.cookies:
        resp.set_cookie("visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp

# @router.get("/_debug/views")
# async def debug_views():
#     # Uwaga: tylko do lokalnych testów / wyłącz na produkcji
#     return {
#         "pending": _VIEW_PENDING,
#         "seen_size": len(_VIEW_SEEN),
#     }


app.include_router(router)
