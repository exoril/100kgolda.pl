import re
from typing import Any
import html

MAX_TOC_TITLE_LENGTH = 25
_NUM_PREFIX_RE = re.compile(r"^\s*\d+(?:[\.\)\-–—]\d+)*\s*[\.\)\-–—:]?\s*")

_PL_MAP = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ż": "z", "ź": "z",
    "Ą": "a", "Ć": "c", "Ę": "e", "Ł": "l", "Ń": "n", "Ó": "o", "Ś": "s", "Ż": "z", "Ź": "z",
})

_heading_re = re.compile(r"(<h([2-4])\b[^>]*>)(.*?)(</h\2>)", re.IGNORECASE | re.DOTALL)
_tag_re = re.compile(r"<[^>]+>")

def _strip_number_prefix(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text).strip()


def _truncate(text: str, max_len: int = MAX_TOC_TITLE_LENGTH) -> str:
    text = " ".join(text.split())  # usuwa wielokrotne spacje/newline
    if len(text) <= max_len:
        return text
    # utnij na granicy słowa, jeśli się da
    cut = text[:max_len].rsplit(" ", 1)[0]
    if len(cut) < max_len * 0.6:  # gdy nie ma spacji / bardzo długie słowo
        cut = text[:max_len]
    return cut + "…"


def _strip_tags(s: str) -> str:
    s = _tag_re.sub("", s).strip()
    s = html.unescape(s)  # <- zamienia &ndash; na –
    return s

def _slugify(text: str) -> str:
    s = text.translate(_PL_MAP).lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s or "sekcja"

def _ensure_id(open_tag: str, new_id: str) -> str:
    # jeśli już ma id, zostaw
    if re.search(r'\bid\s*=\s*["\']', open_tag, re.IGNORECASE):
        return open_tag
    # wstrzyknij id przed '>'
    return open_tag[:-1] + f' id="{new_id}">'

def build_toc(html: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Zwraca (html_z_id, toc_items)
    toc_items: [{level: 2|3|4, id: str, text: str, full_text: str}, ...]
    """
    used: dict[str, int] = {}
    toc: list[dict[str, Any]] = []

    def repl(match: re.Match) -> str:
        open_tag, level, inner, close_tag = (
            match.group(1),
            int(match.group(2)),
            match.group(3),
            match.group(4),
        )

        # Tekst nagłówka: bez tagów + unescape encji HTML
        raw_text = _strip_tags(inner)  # _strip_tags powinien robić html.unescape(...)
        if not raw_text:
            return match.group(0)

        # Usuń numerację typu "1.", "2)", "1.2.3 -", itd.
        clean_text = _strip_number_prefix(raw_text)
        if not clean_text:
            clean_text = raw_text  # fallback

        # Anchor id robimy na czystym tekście (ładniejsze URL-e)
        base = _slugify(clean_text)
        n = used.get(base, 0) + 1
        used[base] = n
        anchor_id = base if n == 1 else f"{base}-{n}"

        # Jeśli nagłówek ma już id, nie nadpisujemy go
        existing_id = None
        m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', open_tag, re.IGNORECASE)
        if m:
            existing_id = m.group(1)

        final_id = existing_id or anchor_id
        new_open = _ensure_id(open_tag, final_id)  # _ensure_id zostawia istniejące id

        toc.append({
            "level": level,
            "id": final_id,
            "text": _truncate(clean_text),
            "full_text": clean_text,
        })

        return f"{new_open}{inner}{close_tag}"

    new_html = _heading_re.sub(repl, html)

    toc.append({
        "level": 2,
        "id": "comments",
        "text": "Komentarze",
        "full_text": "Komentarze",
    })

    return new_html, toc
