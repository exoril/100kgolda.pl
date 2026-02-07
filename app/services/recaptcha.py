# app/services/recaptcha.py
from typing import Optional
import httpx
from app.core.config import RECAPTCHA_SECRET_KEY

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

async def verify_recaptcha(token: str, remote_ip: Optional[str] = None) -> bool:
    if not token:
        return False

    data = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    async with httpx.AsyncClient(timeout=5.0) as c:
        resp = await c.post(VERIFY_URL, data=data)

    if resp.status_code != 200:
        return False

    payload = resp.json() or {}
    return bool(payload.get("success"))
