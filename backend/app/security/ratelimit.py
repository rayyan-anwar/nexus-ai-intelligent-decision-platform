"""Small in-process sliding-window rate limiter (per key). Use a shared store for multi-instance deployments."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, *, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``. ``limit == 0`` disables limiting."""
        if self.limit <= 0:
            return True, 0
        now = self.clock()
        with self._lock:
            if len(self._hits) >= self.max_keys and key not in self._hits:
                self._evict(now)
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (now - q[0])) + 1)
            q.append(now)
            return True, 0

    def _evict(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:  # still full: drop the oldest half
            for k in list(self._hits)[: self.max_keys // 2]:
                del self._hits[k]
