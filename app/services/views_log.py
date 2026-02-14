# app/services/views_log.py
import os, json, asyncio
from datetime import datetime, timezone
from typing import Set, Tuple

VIEWS_LOG_PATH = os.getenv("VIEWS_LOG_PATH", "data/views.log.jsonl")

_seen: Set[Tuple[str, str]] = set()
_lock = asyncio.Lock()

def _ensure_dir():
    os.makedirs(os.path.dirname(VIEWS_LOG_PATH) or ".", exist_ok=True)

async def load_seen_from_log(max_lines: int | None = None) -> None:
    """
    (Opcjonalne) odtwarzanie RAM z pliku na starcie.
    Jeśli log będzie ogromny, ustaw max_lines (np. ostatnie 2 mln).
    """
    if not os.path.exists(VIEWS_LOG_PATH):
        return
    _ensure_dir()
    async with _lock:
        with open(VIEWS_LOG_PATH, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if max_lines and i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    _seen.add((rec["post_id"], rec["vid"]))
                except Exception:
                    continue

async def try_log_unique_view(post_id: str, vid: str) -> bool:
    """
    True -> nowy (pierwszy raz widzimy post_id+vid w tej instancji / po odtworzeniu)
    False -> już było
    """
    if not post_id or not vid:
        return False

    key = (post_id, vid)
    async with _lock:
        if key in _seen:
            return False
        _seen.add(key)

        _ensure_dir()
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "post_id": post_id,
            "vid": vid,
        }
        with open(VIEWS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        return True
