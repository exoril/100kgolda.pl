# app/web/toc.py
import re
import html
from typing import List, Tuple, Dict

H_RE = re.compile(r"<h([2-4])([^>]*)>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
ID_RE = re.compile(r'\sid\s*=\s*"([^"]+)"', re.IGNORECASE)

NUM_PREFIX_RE = re.compile(
    r"""^\s*                      # początek + spacje
        (?:\(?\d+(?:[\.\)]\d+)*\)?) # 1, 1., 1), (1), 1.2, 1.2.3, (1.2)
        \s*                       # spacje
        (?:[.\)\-–—:]\s*)?        # separator: ., ), -, – , —, :
    """,
    re.VERBOSE,
)

def _strip_leading_numbers(title: str) -> str:
    return NUM_PREFIX_RE.sub("", title or "").strip()


def _strip_tags(x: str) -> str:
    # usuwa tagi i dekoduje encje HTML (&ndash; -> –)
    return html.unescape(TAG_RE.sub("", x or "")).strip()

def _slugify(text: str) -> str:
    t = _strip_tags(text).lower()
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"[^a-z0-9\-ąćęłńóśźż]", "", t)
    return t.strip("-") or "sekcja"

def build_toc(html_content: str, include_comments: bool = True) -> Tuple[str, List[Dict[str, str]]]:
    """
    Zwraca: (html_z_id, toc)
    toc = [{"level": "2"/"3"/"4", "id": "...", "title": "..."}]
    """
    if not html_content:
        toc = []
        if include_comments:
            toc.append({"level": "2", "id": "comments", "title": "Komentarze"})
        return "", toc

    toc: List[Dict[str, str]] = []
    used: dict[str, int] = {}

    def repl(m: re.Match) -> str:
        level = m.group(1)
        attrs = m.group(2) or ""
        inner = m.group(3) or ""

        title = _strip_leading_numbers(_strip_tags(inner))
        if not title:
            return m.group(0)


        # jeśli już jest id w atrybutach, użyj go
        m_id = ID_RE.search(attrs)
        if m_id:
            hid = m_id.group(1)
        else:
            base = _slugify(title)
            n = used.get(base, 0)
            used[base] = n + 1
            hid = base if n == 0 else f"{base}-{n+1}"
            attrs = f'{attrs} id="{hid}"'

        toc.append({"level": level, "id": hid, "title": title})
        return f"<h{level}{attrs}>{inner}</h{level}>"

    new_html = H_RE.sub(repl, html_content)

    # ✅ na koniec dopnij komentarze
    if include_comments:
        toc.append({"level": "2", "id": "comments", "title": "Komentarze"})

    return new_html, toc
