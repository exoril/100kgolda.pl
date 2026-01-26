import re, html, math
from datetime import datetime

from app.core.config import PB_URL, POSTS_COLLECTION, SERIES_COLLECTION
from app.pb.client import get_client
from app.pb.comments import get_comment_count_for_post  # (będzie w comments.py)

MAX_EXCERPT_LENGTH = 500

def strip_html(html_text: str) -> str:
    text = re.sub(r"<[^>]*>", "", html_text)
    text = html.unescape(text)
    return text

def format_date_pl(date_str: str) -> str:
    months = [
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
        "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
    ]
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return f"{dt.day} {months[dt.month - 1]} {dt.year}r"

def estimate_reading_time(content: str, words_per_minute: int = 200) -> int:
    text = re.sub(r"<[^>]*>", "", content)
    words = text.split()
    minutes = math.ceil(len(words) / words_per_minute)
    return max(minutes, 1)

def get_thumbnail_url(post: dict):
    thumbs = post.get("thumbnail")
    if not thumbs:
        return None
    filename = thumbs
    return f"{PB_URL}/api/files/{POSTS_COLLECTION}/{post.get('id')}/{filename}"


async def normalize_post(post: dict) -> dict:
    # --- SERIA ---
    series_field = post.get("series")
    if series_field:
        if isinstance(series_field, list) and series_field:
            series_id = series_field[0].get("id")
        elif isinstance(series_field, dict):
            series_id = series_field.get("id")
        elif isinstance(series_field, str):
            series_id = series_field
        else:
            series_id = None

        if series_id:
            client = await get_client()
            series_url = f"/api/collections/{SERIES_COLLECTION}/records/{series_id}"
            series_resp = await client.get(series_url)
            if series_resp.status_code == 200:
                series_data = series_resp.json()
                suffix = series_data.get("suffix", "")
                description = series_data.get("description", "")

                if suffix:
                    post["title"] = post.get("title", "") + f" {suffix}"

                if description:
                    post["content"] = post.get("content", "") + f"<hr><br>{description}"
            else:
                print("Błąd pobrania serii:", series_resp.status_code, series_resp.text)

    # --- KOMENTARZE (licznik) ---
    comment_count = await get_comment_count_for_post(post.get("id"))

    return {
        "id": post.get("id"),
        "title": post.get("title", ""),
        "slug": post.get("slug", ""),
        "category": post.get("category", "Bez kategorii"),
        "created": format_date_pl(post.get("created", datetime.now().isoformat())),
        "seo_date": post.get("created", datetime.now().isoformat())[:10],
        "thumbnail": get_thumbnail_url(post),
        "content": post.get("content", ""),
        "creator": post.get("creator", "Nieznany autor"),
        "views": post.get("views", 0),
        "reading_time": estimate_reading_time(post.get("content", "")),
        "comment_count": comment_count,
    }
