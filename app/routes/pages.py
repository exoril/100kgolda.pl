from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER
from urllib.parse import quote

from app.web.render import render_template
from app.services.recaptcha import verify_recaptcha
from app.services.mailer import send_contact_email
from app.core.config import RECAPTCHA_SITE_KEY
from app.pb.repos.contact_messages import (
    get_last_contact_created,
    log_contact_message,
)

COOLDOWN_CONTACT_SECONDS = 600  # 10 min

router = APIRouter()


@router.get("/o-mnie", response_class=HTMLResponse)
async def o_mnie(request: Request):
    return await render_template(request, request.app.state.templates, "o-mnie.html", {})


@router.get("/o-blogu", response_class=HTMLResponse)
async def o_blogu(request: Request):
    return await render_template(request, request.app.state.templates, "o-blogu.html", {})


@router.get("/moje-projekty", response_class=HTMLResponse)
async def moje_projekty(request: Request):
    return await render_template(request, request.app.state.templates, "moje-projekty.html", {})

@router.get("/warunki", response_class=HTMLResponse)
async def regulamin(request: Request):
    return await render_template(request, request.app.state.templates, "warunki.html", {})

@router.get("/polityka-prywatnosci", response_class=HTMLResponse)
async def polityka_prywatnosci(request: Request):
    return await render_template(request, request.app.state.templates, "polityka-prywatnosci.html", {})

@router.get("/kontakt", response_class=HTMLResponse)
async def kontakt_get(
    request: Request,
    sent: int = 0,
    captcha: int = 0,
    cooldown: int = 0,
    name: str = "",
    email: str = "",
    subject: str = "",
    message: str = "",
):
    return await render_template(
        request,
        request.app.state.templates,
        "kontakt.html",
        {
            "recaptcha_site_key": RECAPTCHA_SITE_KEY,
            "sent_ok": (sent == 1),
            "captcha_error": (captcha == 1),
            "cooldown_s": int(cooldown or 0),
            "prefill_name": name,
            "prefill_email": email,
            "prefill_subject": subject,
            "prefill_message": message,
        },
    )


@router.post("/kontakt")
async def kontakt_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    recaptcha_token: str = Form("", alias="g-recaptcha-response"),
):
    name = (name or "").strip()
    email = (email or "").strip()
    subject = (subject or "").strip()
    message = (message or "").strip()

    # prosta walidacja
    if not name or not email or not subject or not message:
        raise HTTPException(status_code=400, detail="Brak wymaganych pól")

    # captcha
    ok_captcha = await verify_recaptcha(
        recaptcha_token,
        remote_ip=(request.client.host if request.client else None),
    )
    if not ok_captcha:
        n = quote(name)
        e = quote(email)
        s = quote(subject)
        m = quote(message)
        return RedirectResponse(
            url=f"/kontakt?captcha=1&name={n}&email={e}&subject={s}&message={m}#kontakt",
            status_code=HTTP_303_SEE_OTHER,
        )

    # visitor id (z middleware lub cookies)
    vid = (
        getattr(request.state, "visitor_id", None)
        or (request.cookies.get("vid") or "").strip()
        or None
    )

    # ✅ LIMIT: 1 wiadomość / 10 min na visitor_id
    if vid:
        last_created = await get_last_contact_created(vid)
        if last_created is not None:
            # upewnij się, że ma TZ
            if last_created.tzinfo is None:
                last_created = last_created.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            delta = (now - last_created).total_seconds()
            if delta < COOLDOWN_CONTACT_SECONDS:
                wait = int(COOLDOWN_CONTACT_SECONDS - delta)
                n = quote(name)
                e = quote(email)
                s = quote(subject)
                m = quote(message)
                return RedirectResponse(
                    url=f"/kontakt?cooldown={wait}&name={n}&email={e}&subject={s}&message={m}#kontakt",
                    status_code=HTTP_303_SEE_OTHER,
                )

    remote_ip = request.client.host if request.client else None

    # ✅ Zapisz log wysyłki do PB (żeby cooldown działał nawet po restarcie)
    # (Jeśli chcesz nie trzymać treści w PB, w repo możesz ją pominąć / zanonimizować)
    try:
        await log_contact_message(
            name=name,
            email=email,
            subject=subject,
            message=message,
            visitor_id=vid,
            ip=remote_ip,
        )
    except Exception:
        # nawet jeśli log się nie zapisze, mail nadal może pójść;
        # nie blokujemy użytkownika błędem 500
        pass

    # wyślij email
    await send_contact_email(
        name=name,
        email=email,
        subject=subject,
        message=message,
        visitor_id=vid,
        remote_ip=remote_ip,  # możesz usunąć
    )

    return RedirectResponse(url="/kontakt?sent=1#kontakt", status_code=HTTP_303_SEE_OTHER)
