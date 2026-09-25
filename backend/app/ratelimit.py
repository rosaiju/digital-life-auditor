"""Small in-memory sliding-window rate limiter for the auth endpoints.

State is per process, which is enough to blunt password guessing against a single API
instance. Behind several replicas, put a shared limiter (e.g. at the reverse proxy) in front.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings

_WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    def __init__(self, window: float = _WINDOW_SECONDS):
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> float:
        """Record a hit. Returns 0 if allowed, else the seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= limit:
                return self.window - (now - hits[0])
            hits.append(now)
            if len(self._hits) > 10_000:  # drop idle keys so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    del self._hits[k]
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


auth_limiter = SlidingWindowLimiter()


def limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle auth attempts per client address."""
    limit = settings.auth_rate_limit_per_minute
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    retry_after = auth_limiter.check(f"{client}:{request.url.path}", limit)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts, try again shortly",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
