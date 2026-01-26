import asyncio
import re
from fastapi import Request
from fastapi.templating import Jinja2Templates
from app.pb.posts import (
    get_post_count,
    get_top_viewed_posts,
    get_all_categories,
    get_top_commented_posts
)

IMG_RE = re.compile(r"<img(?![^>]*\sloading=)([^>]*)(/?)>", re.IGNORECASE)

def lazy_images(html: str) -> str:
    if not html:
        return ""
    return IMG_RE.sub(r'<img loading="lazy" decoding="async"\1\2>', html)

# funkcja renderująca template z ogólnodostępnym kotekstem
async def render_template(request, templates, template_name, context=None):
    post_count, top_posts, categories, top_commented = await asyncio.gather(
        get_post_count(),
        get_top_viewed_posts(3),
        get_all_categories(),
        get_top_commented_posts(3),
    )

    ctx = {
        "request": request,
        "post_count": post_count,
        "top_posts": top_posts,
        "categories": categories,
        "top_commented": top_commented,
        "lazy_images": lazy_images,
    }
    if context:
        ctx.update(context)

    return templates.TemplateResponse(template_name, ctx)


def render_pagination(
    request: Request,
    templates: Jinja2Templates,
    page: int,
    total_pages: int,
    base_url: str,
) -> str:
    return templates.get_template("partials/pagination.html").render(
        page=page,
        total_pages=total_pages,
        base_url=base_url,
        request=request,
    )
