"""In-memory daily usage accounting with reserve / commit / release.

All state changes happen under one asyncio.Lock. Counts reset at UTC
midnight and on restart. Judge counts are separate per browser and never
touch the global count.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone

SECONDS_PER_DAY = 86400


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LimitReached(Exception):
    """Raised by reserve(). `code` is 'visitor_limit' or 'global_cap'."""

    def __init__(self, code: str, retry_after_seconds: int):
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class Reservation:
    browser_id: str
    is_judge: bool
    day: date
    id: str = field(default_factory=lambda: uuid4().hex)


class UsageTracker:
    def __init__(self, settings, clock=utc_now):
        self._settings = settings
        self._clock = clock
        self._lock = asyncio.Lock()
        self._day = clock().date()
        self._reset_counts()

    def _reset_counts(self) -> None:
        self._visitor: dict[str, int] = defaultdict(int)
        self._judge: dict[str, int] = defaultdict(int)
        self._global = 0
        self._pending_visitor: dict[str, set[str]] = defaultdict(set)
        self._pending_judge: dict[str, set[str]] = defaultdict(set)
        self._pending_global: set[str] = set()

    def _roll_day(self) -> None:
        today = self._clock().date()
        if today != self._day:
            self._day = today
            self._reset_counts()

    def _limit(self, is_judge: bool) -> int:
        s = self._settings
        return s.judge_daily_limit if is_judge else s.visitor_daily_limit

    def _used(self, browser_id: str, is_judge: bool) -> int:
        if is_judge:
            return self._judge[browser_id] + len(self._pending_judge[browser_id])
        return self._visitor[browser_id] + len(self._pending_visitor[browser_id])

    def _seconds_until_reset(self) -> int:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        midnight = datetime.combine(
            now.date() + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo
        )
        seconds = int((midnight - now).total_seconds())
        if (midnight - now).total_seconds() > seconds:
            seconds += 1  # round up so the value stays > 0
        return max(1, min(SECONDS_PER_DAY, seconds))

    async def reserve(self, browser_id: str, is_judge: bool) -> Reservation:
        async with self._lock:
            self._roll_day()
            reset = self._seconds_until_reset()
            if self._used(browser_id, is_judge) >= self._limit(is_judge):
                raise LimitReached("visitor_limit", reset)
            if (
                not is_judge
                and self._global + len(self._pending_global) >= self._settings.global_daily_cap
            ):
                raise LimitReached("global_cap", reset)
            r = Reservation(browser_id, is_judge, self._day)
            if is_judge:
                self._pending_judge[browser_id].add(r.id)
            else:
                self._pending_visitor[browser_id].add(r.id)
                self._pending_global.add(r.id)
            return r

    def _drop_pending(self, r: Reservation) -> bool:
        """Remove this reservation's pending id. False if unknown or stale."""
        if r.day != self._day:
            return False
        pending = self._pending_judge if r.is_judge else self._pending_visitor
        ids = pending.get(r.browser_id)
        if not ids or r.id not in ids:
            return False
        ids.discard(r.id)
        if not ids:
            del pending[r.browser_id]
        self._pending_global.discard(r.id)
        return True

    async def commit(self, r: Reservation) -> None:
        async with self._lock:
            self._roll_day()
            if not self._drop_pending(r):
                return
            if r.is_judge:
                self._judge[r.browser_id] += 1
            else:
                self._visitor[r.browser_id] += 1
                self._global += 1

    async def release(self, r: Reservation) -> None:
        async with self._lock:
            self._roll_day()
            self._drop_pending(r)

    async def remaining(self, browser_id: str, is_judge: bool) -> int:
        async with self._lock:
            self._roll_day()
            return max(0, self._limit(is_judge) - self._used(browser_id, is_judge))

    async def seconds_until_reset(self) -> int:
        async with self._lock:
            self._roll_day()
            return self._seconds_until_reset()
