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

async def count_unique_view(request: Request, response: Response, post_id: str) -> None:
    visitor_id = getattr(request.state, "visitor_id", None)
    if not visitor_id:
        return 

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
