import time
from typing import Any, Dict, Tuple

_cache: Dict[str, Tuple[float, Any]] = {}

def cache_get(key: str, ttl: int):
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > ttl:
        _cache.pop(key, None)
        return None
    return value

def cache_set(key: str, value: Any):
    _cache[key] = (time.time(), value)
