import time

from app.core.errors import DomainError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        recent = [stamp for stamp in self._hits.get(key, []) if now - stamp < window_seconds]
        if len(recent) >= limit:
            raise DomainError("RATE_LIMITED", "Too many requests.", 429)
        recent.append(now)
        self._hits[key] = recent
