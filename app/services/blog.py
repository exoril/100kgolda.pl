import re, html, math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import httpx
from collections import Counter

from app.core.config import PB_URL, POSTS_COLLECTION, COMMENTS_COLLECTION
from app.pb.repos import posts as posts_repo
from app.pb.repos.series import get_series_suffix, get_series

MAX_EXCERPT_LENGTH = 500

from app.services.views_log import try_log_unique_view
from app.pb.repos.posts import pb_increment_post_views

async def register_unique_view(post_id: str, vid: str) -> None:
    if await try_log_unique_view(post_id, vid):
        await pb_increment_post_views(post_id)

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
    months = [
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
        "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
    ]
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
        "views": int(post.get("views") or 0),
        "comments": 0,
    }



async def list_posts(page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.list_posts(page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    return posts, total_pages


async def search_posts(q: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.search_posts(q, page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    return posts, total_pages


async def posts_by_category(category: str, page: int = 1, per_page: int = 5) -> Tuple[List[Dict[str, Any]], int]:
    raw, total_pages = await posts_repo.list_posts_by_category(category, page, per_page)
    posts = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw]))
    return posts, total_pages

async def get_comments_count_for_post(post_id: str, approved_only: bool = True) -> int:
    """
    Zwraca liczbę komentarzy dla posta, bez pobierania całej listy.
    Korzysta z totalItems z PocketBase.
    """
    if not post_id:
        return 0

    if approved_only:
        filter_str = f'post="{post_id}" && approved = true'
    else:
        filter_str = f'post="{post_id}"'

    params = {
        "page": 1,
        "perPage": 1,     # minimalny payload
        "fields": "id",   # minimalny payload
        "filter": filter_str,
    }

    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(
            f"{PB_URL}/api/collections/{COMMENTS_COLLECTION}/records",
            params=params,
        )
        r.raise_for_status()
        data = r.json()

    return int(data.get("totalItems") or 0)


async def get_post(slug: str) -> Optional[Dict[str, Any]]:
    raw = await posts_repo.get_post_by_slug(slug)
    if not raw:
        return None

    post = await normalize_post_raw(raw)

    # NEW: policz zatwierdzone komentarze
    post["comments"] = await get_comments_count_for_post(post["id"], approved_only=True)

    return post



async def get_post_count() -> int:
    return await posts_repo.get_post_count()


async def get_all_categories() -> List[str]:
    return await posts_repo.list_categories()


async def _pb_fetch_all_post_refs(
    collection: str,
    *,
    relation_field: str = "post",
    filter_str: str | None = None,
    per_page: int = 200,
    timeout: float = 10.0,
) -> List[str]:
    """
    Pobiera wszystkie rekordy z danej kolekcji, zwracając listę ID postów z pola relacyjnego `relation_field`.
    Ściąga tylko jedno pole (fields=post) żeby było lekko.
    """
    post_ids: List[str] = []
    page = 1

    params_base: Dict[str, Any] = {
        "perPage": per_page,
        "fields": relation_field,
    }
    if filter_str:
        params_base["filter"] = filter_str

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            params = dict(params_base)
            params["page"] = page

            r = await client.get(
                f"{PB_URL}/api/collections/{collection}/records",
                params=params,
            )
            r.raise_for_status()
            data = r.json()

            items = data.get("items") or []
            for it in items:
                pid = it.get(relation_field)
                if isinstance(pid, str) and pid:
                    post_ids.append(pid)

            total_pages = data.get("totalPages") or 1
            if page >= total_pages:
                break
            page += 1

    return post_ids


def _build_or_filter_for_ids(ids: List[str]) -> str:
    safe = [i.replace('"', '\\"') for i in ids]
    return " || ".join([f'id="{i}"' for i in safe])


async def _fetch_posts_by_ids(ids: List[str]) -> List[Dict[str, Any]]:
    if not ids:
        return []

    filter_str = _build_or_filter_for_ids(ids)
    params = {
        "page": 1,
        "perPage": len(ids),
        "filter": filter_str,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records",
            params=params,
        )
        r.raise_for_status()
        data = r.json()

    return data.get("items") or []


async def _get_top_posts_by_related_count(
    source_collection: str,
    *,
    filter_str: str | None,
    limit: int,
    count_field: str,
) -> List[Dict[str, Any]]:
    """
    Liczy top posty na podstawie ilości rekordów w source_collection (np. comments)
    i zapisuje wynik w polu `count_field` (np. "comments").
    """
    limit = max(1, int(limit))

    post_refs = await _pb_fetch_all_post_refs(
        source_collection,
        relation_field="post",
        filter_str=filter_str,
    )
    if not post_refs:
        return []

    counts = Counter(post_refs)
    top_ids = [pid for pid, _cnt in counts.most_common(limit)]
    if not top_ids:
        return []

    raw_posts = await _fetch_posts_by_ids(top_ids)
    normalized = list(await asyncio.gather(*[normalize_post_raw(p) for p in raw_posts]))

    # zachowaj kolejność + dopisz count
    by_id = {p["id"]: p for p in normalized if p.get("id")}
    out: List[Dict[str, Any]] = []
    for pid in top_ids:
        p = by_id.get(pid)
        if not p:
            continue
        p[count_field] = int(counts.get(pid, 0))
        out.append(p)

    return out


async def get_top_commented_posts(limit: int = 3) -> List[Dict[str, Any]]:
    return await _get_top_posts_by_related_count(
        COMMENTS_COLLECTION,
        filter_str="approved = true",
        limit=limit,
        count_field="comments",
    )


async def get_top_viewed_posts(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Zwraca top posty po polu liczbowym `views`, ale tylko opublikowane (published=true).
    """
    params = {
        "page": 1,
        "perPage": max(1, int(limit)),
        "sort": "-views",
        "filter": "published=true",
        # opcjonalnie:
        # "fields": "id,title,slug,category,created,thumbnail,content,creator,meta_description,comments_on,series,views,published",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records",
            params=params,
        )
        r.raise_for_status()
        data = r.json()

    items = data.get("items") or []
    if not items:
        return []

    return list(await asyncio.gather(*[normalize_post_raw(p) for p in items]))



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
