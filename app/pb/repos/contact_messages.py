# app/pb/repos/contact_messages.py
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.core.config import CONTACT_MESSAGES_COLLECTION
from app.pb.client import pb_request


def pb_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _parse_pb_dt(s: str) -> Optional[datetime]:
    """
    PocketBase zwykle zwraca ISO z 'Z' (UTC).
    Zwracamy datetime z tzinfo (UTC).
    """
    if not s:
        return None
    s = (s or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def get_last_contact_created(visitor_id: str) -> Optional[datetime]:
    """
    Zwraca datetime (UTC) ostatniej wiadomości kontaktowej wysłanej przez visitor_id.
    """
    if not visitor_id:
        return None

    vid = pb_escape(visitor_id)
    url = f"/api/collections/{CONTACT_MESSAGES_COLLECTION}/records"
    params = {
        "filter": f'visitor_id="{vid}"',
        "sort": "-created",
        "perPage": 1,
        "page": 1,
        "fields": "created",
    }

    resp = await pb_request("GET", url, params=params)
    if resp.status_code != 200:
        return None

    items = (resp.json() or {}).get("items") or []
    if not items:
        return None

    return _parse_pb_dt(items[0].get("created") or "")


async def log_contact_message(
    name: str,
    email: str,
    subject: str,
    message: str,
    visitor_id: Optional[str],
    ip: Optional[str] = None,
) -> bool:
    """
    Zapisuje rekord do kolekcji contact_messages (głównie pod cooldown / audyt).
    Zwraca True jeśli zapisano.
    """
    url = f"/api/collections/{CONTACT_MESSAGES_COLLECTION}/records"

    payload: Dict[str, Any] = {
        "name": (name or "").strip(),
        "email": (email or "").strip(),
        "subject": (subject or "").strip(),
        "message": (message or "").strip(),
    }

    if visitor_id:
        payload["visitor_id"] = visitor_id
    if ip:
        payload["ip"] = ip

    resp = await pb_request("POST", url, json=payload)
    return resp.status_code in (200, 201)
