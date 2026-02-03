# app/cache.py
import time
import asyncio
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple, List

@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    expired: int = 0

class TTLCache:
    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self.stats = CacheStats()

    async def get(self, key: str) -> Optional[Any]:
        now = time.time()
        async with self._lock:
            item = self._data.get(key)
            if not item:
                self.stats.misses += 1
                return None

            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                self.stats.expired += 1
                self.stats.misses += 1
                return None

            self.stats.hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.time() + max(int(ttl), 1)
        async with self._lock:
            self._data[key] = (expires_at, value)
            self.stats.sets += 1

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self.stats.deletes += 1

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    async def snapshot(self) -> Dict[str, Any]:
        # krótki “podgląd” stanu cache (ile kluczy, staty)
        async with self._lock:
            return {
                "items": len(self._data),
                "stats": asdict(self.stats),
            }

# globalna instancja (per worker)
cache = TTLCache()

def key(*parts: Any) -> str:
    # prosty generator kluczy
    return ":".join(str(p) for p in parts if p is not None)
