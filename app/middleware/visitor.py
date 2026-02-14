import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

VID_COOKIE = "vid"
VID_MAX_AGE = 60 * 60 * 24 * 365  # 1 rok

class VisitorIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        vid = request.cookies.get(VID_COOKIE)

        if not vid or len(vid) < 16:
            vid = uuid.uuid4().hex
            request.state._set_vid_cookie = vid

        request.state.visitor_id = vid

        response: Response = await call_next(request)

        new_vid = getattr(request.state, "_set_vid_cookie", None)
        if new_vid:
            response.set_cookie(
                key=VID_COOKIE,
                value=new_vid,
                max_age=VID_MAX_AGE,
                samesite="lax",
                httponly=False,
                # secure=True  # włączysz dopiero jak będziesz mieć HTTPS
            )

        return response
