import asyncio
from app.pb.repos.comments import count_comments
from app.pb.repos.views import count_views
from app.pb.repos.stats import update_stats_totals

async def rebuild_post_stats(post_id: str) -> None:
    comments_total, views_total = await asyncio.gather(
        count_comments(post_id),
        count_views(post_id),
    )

    await update_stats_totals(
        post_id,
        views_total=views_total,
        comments_total=comments_total,
    )
