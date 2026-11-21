"""Judge pass check with constant-time compare and per-browser lockout.

State is in memory only. The pass value is never logged or returned.
"""
from __future__ import annotations

import asyncio
import hmac
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.usage import utc_now

MAX_PASS_LENGTH = 128
MAX_WRONG_ATTEMPTS = 5
LOCKOUT = timedelta(hours=1)


@dataclass(frozen=True)
class JudgeResult:
    """status is 'valid', 'invalid' or 'locked'."""

    status: str
    retry_after_seconds: int | None = None

    @property
    def valid(self) -> bool:
        return self.status == "valid"

    @property
    def locked(self) -> bool:
        return self.status == "locked"


class JudgeGuard:
    def __init__(self, settings, clock=utc_now):
        self._settings = settings
        self._clock = clock
        self._lock = asyncio.Lock()
        self._wrong: dict[str, int] = {}
        self._locked_until: dict[str, datetime] = {}

    def is_valid(self, presented: str) -> bool:
        # Trim both sides so pasted whitespace/newlines do not cause a mismatch.
        configured = (self._settings.judge_pass or "").strip()
        presented = (presented or "").strip()
        if not configured or not presented or len(presented) > MAX_PASS_LENGTH:
            return False
        return hmac.compare_digest(presented.encode(), configured.encode())

    async def verify(self, browser_id: str, presented: str) -> JudgeResult:
        async with self._lock:
            now = self._clock()
            until = self._locked_until.get(browser_id)
            if until is not None:
                if now < until:
                    return JudgeResult("locked", self._retry_after(until, now))
                del self._locked_until[browser_id]
                self._wrong.pop(browser_id, None)
            if self.is_valid(presented):
                return JudgeResult("valid")
            count = self._wrong.get(browser_id, 0) + 1
            if count >= MAX_WRONG_ATTEMPTS:
                self._wrong.pop(browser_id, None)
                self._locked_until[browser_id] = now + LOCKOUT
            else:
                self._wrong[browser_id] = count
            return JudgeResult("invalid")

    @staticmethod
    def _retry_after(until: datetime, now: datetime) -> int:
        return max(1, math.ceil((until - now).total_seconds()))
