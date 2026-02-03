# app/pb/metrics.py
import asyncio
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import time

_lock = asyncio.Lock()

@dataclass
class MetricRow:
    key: str
    count: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float

_counts = defaultdict(int)
_total_ms = defaultdict(float)
_min_ms = defaultdict(lambda: float("inf"))
_max_ms = defaultdict(float)
_statuses = defaultdict(int)

_started_at = time.time()

def _bucket(method: str, path: str) -> str:
    """
    Grupowanie: GET posts / GET post_stats / GET comments itd.
    PocketBase: /api/collections/{collection}/...
    """
    parts = path.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "collections":
        coll = parts[2]
        return f"{method} {coll}"
    return f"{method} {path}"

async def record(method: str, path: str, status: int, ms: float) -> None:
    k = _bucket(method, path)
    async with _lock:
        _counts[k] += 1
        _total_ms[k] += ms
        _min_ms[k] = min(_min_ms[k], ms)
        _max_ms[k] = max(_max_ms[k], ms)
        _statuses[str(status)] += 1

async def snapshot() -> Dict[str, Any]:
    async with _lock:
        rows: List[MetricRow] = []
        for k, c in _counts.items():
            total = _total_ms[k]
            avg = total / c if c else 0.0
            rows.append(MetricRow(
                key=k,
                count=c,
                total_ms=round(total, 1),
                avg_ms=round(avg, 1),
                min_ms=round(_min_ms[k] if _min_ms[k] != float("inf") else 0.0, 1),
                max_ms=round(_max_ms[k], 1),
            ))

        rows.sort(key=lambda r: r.count, reverse=True)

        total_requests = sum(_counts.values())
        total_time_ms = round(sum(_total_ms.values()), 1)

        return {
            "uptime_s": int(time.time() - _started_at),
            "total_requests": total_requests,
            "total_time_ms": total_time_ms,
            "rows": [asdict(r) for r in rows],
            "statuses": dict(sorted(_statuses.items(), key=lambda x: int(x[0]))),
        }

async def reset() -> None:
    async with _lock:
        _counts.clear()
        _total_ms.clear()
        _min_ms.clear()
        _max_ms.clear()
        _statuses.clear()
