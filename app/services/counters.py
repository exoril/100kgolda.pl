# app/services/counters.py
from datetime import date
from uuid import uuid4
from fastapi import Request
from starlette.responses import Response
from app.pb.repos.views import create_unique_view
from app.pb.repos.stats import increment_views_total
from app.pb.repos.comments import count_comments
from app.pb.repos.stats import update_comments_total

VISITOR_COOKIE = "visitor_id"

def ensure_visitor_cookie(request: Request, response: Response) -> str:
    vid = request.cookies.get(VISITOR_COOKIE)
    if not vid:
        vid = str(uuid4())
        response.set_cookie(
            VISITOR_COOKIE,
            vid,
            max_age=60 * 60 * 24 * 365 * 2,
            httponly=True,
            samesite="lax",
            path="/",          # <-- WAŻNE
        )
    return vid


async def count_unique_view(request: Request, response: Response, post_id: str) -> None:
    """
    1 unikalny użytkownik (cookie) / dzień / post -> +1 do views_total
    """
    visitor_id = ensure_visitor_cookie(request, response)
    day = date.today().isoformat()

    created = await create_unique_view(post_id=post_id, day=day, visitor_id=visitor_id)
    if created:
        await increment_views_total(post_id, by=1)


async def sync_comments_total(post_id: str) -> int:
    """
    comments_total w post_stats = liczba komentarzy approved=true
    """
    count = await count_comments(post_id)
    await update_comments_total(post_id, count)
    return count
