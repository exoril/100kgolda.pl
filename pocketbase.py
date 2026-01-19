import requests
import re
from datetime import datetime 
import html

PB_URL = "http://127.0.0.1:8090"
POSTS_COLLECTION = "posts"
MAX_EXCERPT_LENGTH = 500

def get_post_count():
    url = f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1}
    resp = requests.get(url, params=params)

    if resp.status_code != 200:
        return 0

    data = resp.json()
    return data.get("totalItems", 0)

def strip_html(html_text: str) -> str:
    """Usuwa tagi HTML i dekoduje encje (np. &oacute; → ó)."""
    text = re.sub(r"<[^>]*>", "", html_text)
    text = html.unescape(text)
    return text

def format_date_pl(date_str: str) -> str:
    """Zwraca datę w formacie '12 stycznia 2026r'"""
    months = [
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
        "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
    ]
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return f"{dt.day} {months[dt.month - 1]} {dt.year}r"


def get_thumbnail_url(post):
    thumbs = post.get("thumbnail")
    if not thumbs:
        return None
    filename = thumbs
    return f"{PB_URL}/api/files/{POSTS_COLLECTION}/{post.get('id')}/{filename}"


def normalize_post(post: dict) -> dict:
    content_text = strip_html(post.get("content", ""))
    excerpt = content_text[:MAX_EXCERPT_LENGTH] + "..." if len(content_text) > MAX_EXCERPT_LENGTH else content_text

    return {
        "title": post.get("title", "Brak tytułu"),
        "slug": post.get("slug", ""),
        "category": post.get("category", "Bez kategorii"),
        "created": format_date_pl(post.get("created", datetime.now().isoformat())),
        "seo_date": post.get("created", datetime.now().isoformat())[:10],
        "excerpt": excerpt,
        "thumbnail": get_thumbnail_url(post),
        "content": post.get("content", ""),
        "creator": post.get("creator", "Nieznany autor")
    }



def get_post_by_slug(slug: str):
    url = f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": f'slug = "{slug}"', "perPage": 1}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return None

    items = resp.json().get("items")
    if not items:
        return None

    return normalize_post(items[0])


def get_all_posts(page: int = 1, per_page: int = 5):
    url = f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "sort": "-created", "page": page, "perPage": per_page}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return [], 0

    data = resp.json()
    items = data.get("items", [])
    total_items = data.get("totalItems", 0)
    total_pages = (total_items + per_page - 1) // per_page

    posts = [normalize_post(post) for post in items]
    return posts, total_pages


def get_all_categories():
    url = f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records"
    params = {"filter": "published=true", "perPage": 1000}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return []

    items = resp.json().get("items", [])
    categories = set(post.get("category", "Bez kategorii") for post in items)
    return sorted(categories)


def get_posts_by_category(category: str, page: int = 1, per_page: int = 5):
    """
    Pobiera posty z danej kategorii z paginacją.
    """
    url = f"{PB_URL}/api/collections/{POSTS_COLLECTION}/records"
    params = {
        "filter": f'published=true && category="{category}"',
        "sort": "-created",
        "page": page,
        "perPage": per_page
    }
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return [], 0  # pusta lista + total_pages 0

    data = resp.json()
    items = data.get("items", [])
    total_items = data.get("totalItems", 0)
    total_pages = (total_items + per_page - 1) // per_page

    posts = [normalize_post(post) for post in items]
    return posts, total_pages

