import os

def env(name: str, default: str = "") -> str:
    val = os.getenv(name, default)
    if val == "" and default == "":
        raise RuntimeError(f"Missing env var: {name}")
    return val

PB_URL = env("PB_URL")

POSTS_COLLECTION = env("POSTS_COLLECTION")
COMMENTS_COLLECTION = env("COMMENTS_COLLECTION")
SERIES_COLLECTION = env("SERIES_COLLECTION")
SERVICE_COLLECTION = env("SERVICE_COLLECTION")

RECAPTCHA_SITE_KEY = env("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = env("RECAPTCHA_SECRET_KEY")

PB_SERVICE_EMAIL = env("PB_SERVICE_EMAIL")
PB_SERVICE_PASSWORD = env("PB_SERVICE_PASSWORD")

SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT"))
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
CONTACT_TO = env("CONTACT_TO")
CONTACT_FROM = env("CONTACT_FROM")
