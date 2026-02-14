import re, html, math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import httpx

from app.core.config import PB_URL, POSTS_COLLECTION, COMMENTS_COLLECTION
from app.pb.repos import posts as posts_repo
from app.pb.repos import stats as stats_repo
from app.pb.repos.series import get_series_suffix, get_series


MAX_EXCERPT_LENGTH = 500

def extract_series_id(raw_series):
    if not raw_series:
        return None
    if isinstance(raw_series, str):
        return raw_series
    if isinstance(raw_series, dict):
        return raw_series.get("id")
    if isinstance(raw_series, list) and raw_series:
        first = raw_series[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("id")
    return None



def strip_html(html_text: str) -> str:
    text = re.sub(r"<[^>]*>", "", html_text or "")
    return html.unescape(text)

def format_date_pl(date_str: str) -> str:
    months = ["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca","sierpnia","września","października","listopada","grudnia"]
    dt = datetime.fromisoformat((date_str or datetime.now().isoformat()).replace("Z", "+00:00"))
    return f"{dt.day} {months[dt.month - 1]} {dt.year}r"

def estimate_reading_time(content: str, words_per_minute: int = 200) -> int:
    text = strip_html(content)
    words = text.split()
    minutes = math.ceil(len(words) / words_per_minute) if words else 1
    return max(minutes, 1)

def get_thumbnail_url(post: dict) -> Optional[str]:
    filename = post.get("thumbnail")
    if not filename:
        return None
    return f"{PB_URL}/api/files/{POSTS_COLLECTION}/{post.get('id')}/{filename}"

SERIES_DESC_MARKER = "<!--series-description-->"

async def normalize_post_raw(post: dict) -> Dict[str, Any]:
    content = post.get("content", "") or ""

    title = post.get("title", "") or ""
    series_id = extract_series_id(post.get("series"))

    if series_id:
        series = await get_series(series_id)

        # 1) suffix do tytułu
        suffix = (series.get("suffix") or "").strip()
        if suffix and not title.endswith(suffix):
            title = f"{title} {suffix}".strip()

        # 2) description na koniec contentu
        desc = (series.get("description") or "").strip()
        if desc and SERIES_DESC_MARKER not in content:
            # separator + marker żeby nie doklejać 2x
            content = f"{content}\n<hr>\n{SERIES_DESC_MARKER}\n{desc}"

    return {
        "id": post.get("id"),
        "title": title,
        "slug": post.get("slug", ""),
        "category": post.get("category", "Bez kategorii"),
        "created": format_date_pl(post.get("created")),
        "seo_date": (post.get("created") or "")[:10],
        "thumbnail": get_thumbnail_url(post),
        "content": content,
        "creator": post.get("creator", "Nieznany autor"),
        "reading_time": estimate_reading_time(content),
        "meta_description": post.get("meta_description", ""),
        "comments_on": bool(post.get("comments_on", True)),
    }


async def attach_stats(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ids = [p.get("id") for p in posts if p.get("id")]
    stats_map = await stats_repo.ensure_stats_for_posts(ids)
    for p in posts:
        pid = p.get("id")
        p["stats"] = stats_map.get(pid) or stats_repo.DEFAULT_STATS.copy()
    return posts

async def list_posts(page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.list_posts(page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    posts = await attach_stats(posts)
    return posts, total_pages


async def search_posts(q: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.search_posts(q, page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    posts = await attach_stats(posts)
    return posts, total_pages


async def posts_by_category(category: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.list_posts_by_category(category, page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    posts = await attach_stats(posts)
    return posts, total_pages


async def get_post(slug: str) -> Optional[Dict[str, Any]]:
    raw = await posts_repo.get_post_by_slug(slug)
    if not raw:
        return None

    post = await normalize_post_raw(raw)
    await attach_stats([post])
    return post


async def get_post_count() -> int:
    return await posts_repo.get_post_count()

async def get_all_categories() -> List[str]:
    return await posts_repo.list_categories()

async def get_top_posts_by_stat(stat_field: str, limit: int = 3, scan: int = 50) -> List[Dict[str, Any]]:
    stats_items = await stats_repo.list_stats_sorted(stat_field, limit=scan)
    post_ids = [s.get("post") for s in stats_items if s.get("post")]
    posts_by_id = await posts_repo.fetch_posts_by_ids(post_ids)

    out: List[Dict[str, Any]] = []
    for s in stats_items:
        pid = s.get("post")
        raw_post = posts_by_id.get(pid)
        if not raw_post:
            continue

        # filtruj tylko dla topki komentarzy
        if stat_field == "comments_total" and raw_post.get("comments_on", True) is False:
            continue

        post = await normalize_post_raw(raw_post)
        post["stats"] = s
        out.append(post)

        if len(out) >= limit:
            break

    return out


async def get_top_viewed_posts(limit: int = 3) -> List[Dict[str, Any]]:
    return await get_top_posts_by_stat("views_total", limit=limit)

async def get_top_commented_posts(limit: int = 3) -> List[Dict[str, Any]]:
    return await get_top_posts_by_stat("comments_total", limit=limit)


def _pb_parse_dt(created: str) -> datetime:
    # PocketBase zwykle zwraca ISO, czasem z "Z"
    return datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone.utc)



async def get_last_comment_created_for_post(vid: str, post_id: str) -> datetime | None:
    params = {
        "page": 1,
        "perPage": 1,
        "sort": "-created",
        "fields": "created",
        "filter": f'visitor_id="{vid}" && post="{post_id}"',
    }

    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(
            f"{PB_URL}/api/collections/{COMMENTS_COLLECTION}/records",
            params=params,
        )
        r.raise_for_status()
        data = r.json()

    items = data.get("items") or []
    if not items:
        return None
    return _pb_parse_dt(items[0]["created"])
