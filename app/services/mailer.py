# app/services/mailer.py
from __future__ import annotations

import smtplib
from email.message import EmailMessage
import anyio

from app.core.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    CONTACT_FROM, CONTACT_TO,
)

def _send_sync(msg: EmailMessage) -> None:
    # SMTP SSL (port 465)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

async def send_contact_email(
    *,
    name: str,
    email: str,
    subject: str,
    message: str,
    visitor_id: str | None = None,
    remote_ip: str | None = None,
) -> None:
    """
    Wysyła maila z formularza kontaktowego:
    From: formularz@100kgolda.pl
    To:   marcin@100kgolda.pl
    Reply-To: email użytkownika
    """
    name = (name or "").strip()
    email = (email or "").strip()
    subject = (subject or "").strip()
    message = (message or "").strip()

    msg = EmailMessage()
    msg["From"] = CONTACT_FROM
    msg["To"] = CONTACT_TO
    msg["Subject"] = f"[Kontakt] {subject}"
    if email:
        msg["Reply-To"] = email

    body = (
        f"Imię: {name}\n"
        f"E-mail: {email}\n"
        f"VID: {visitor_id or '-'}\n"
        "\n"
        "Wiadomość:\n"
        "----------------------------------------\n"
        f"{message}\n"
        "----------------------------------------\n"
    )
    msg.set_content(body)

    await anyio.to_thread.run_sync(_send_sync, msg)
