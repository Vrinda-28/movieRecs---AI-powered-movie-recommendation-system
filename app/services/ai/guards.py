"""Guards: Sanitisation, rate-limiting, interpretation TTL cache, and secret redaction."""

import hashlib
import logging
import re
import time
import unicodedata
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.ai import ParsedPreferences

logger = logging.getLogger(__name__)


def sanitize_input_text(text: str) -> str:
    """Strips control characters, collapses whitespace, and trims."""
    if not text:
        return ""
    # Strip non-printable control characters, but allow regular spaces
    cleaned = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )
    # Collapse consecutive whitespace characters into a single space
    collapsed = re.sub(r"\s+", " ", cleaned).strip()
    return collapsed


class UserRateLimiter:
    """In-process sliding-window rate limiter per user."""

    def __init__(self, requests_per_minute: int = 10, window_seconds: float = 60.0):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: Dict[int, deque] = defaultdict(deque)

    def check(self, user_id: int) -> None:
        """Checks rate limit for user_id.

        Raises HTTPException(429) if exceeded.
        """
        now = time.monotonic()
        user_timestamps = self._history[user_id]

        # Evict timestamps outside sliding window
        while user_timestamps and (now - user_timestamps[0]) > self.window_seconds:
            user_timestamps.popleft()

        if len(user_timestamps) >= self.requests_per_minute:
            oldest = user_timestamps[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            logger.warning(
                f"Rate limit exceeded for user_id={user_id}. Retry-After: {retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="ai_rate_limited",
                headers={"Retry-After": str(retry_after)},
            )

        user_timestamps.append(now)

    def reset_for_test(self) -> None:
        """Clears all rate limit state (useful in test teardown)."""
        self._history.clear()


rate_limiter = UserRateLimiter(
    requests_per_minute=settings.AI_RATE_LIMIT_PER_MIN,
    window_seconds=60.0,
)


class InterpretationCache:
    """TTL in-memory cache for prompt interpretation (ParsedPreferences).

    Max 256 entries, 10 min TTL.
    """

    def __init__(self, ttl_seconds: float = 600.0, max_size: int = 256):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, Tuple[float, ParsedPreferences]] = {}

    def _hash_key(self, prompt: str) -> str:
        normalized = sanitize_input_text(prompt).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> Optional[ParsedPreferences]:
        key = self._hash_key(prompt)
        entry = self._cache.get(key)
        if not entry:
            return None
        timestamp, value = entry
        if (time.monotonic() - timestamp) > self.ttl_seconds:
            del self._cache[key]
            return None
        return value

    def set(self, prompt: str, value: ParsedPreferences) -> None:
        now = time.monotonic()
        # Evict expired entries if approaching max size
        if len(self._cache) >= self.max_size:
            keys_to_del = [
                k for k, (ts, _) in self._cache.items() if (now - ts) > self.ttl_seconds
            ]
            for k in keys_to_del:
                del self._cache[k]

            # If still full, pop oldest item
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]

        key = self._hash_key(prompt)
        self._cache[key] = (now, value)

    def clear(self) -> None:
        self._cache.clear()


interpretation_cache = InterpretationCache(ttl_seconds=600.0, max_size=256)
