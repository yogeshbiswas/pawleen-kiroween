import asyncio
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.usage import LimitReached, UsageTracker
from tests.conftest import FakeClock


def make_settings(visitor=3, judge=20, cap=100):
    return Settings(
        openai_api_key="k", image_model="m", vision_model="v", image_quality="medium",
        judge_pass="", visitor_daily_limit=visitor, judge_daily_limit=judge,
        global_daily_cap=cap,
    )  # fmt: skip


async def use(tracker, bid, judge=False):
    r = await tracker.reserve(bid, judge)
    await tracker.commit(r)


async def test_fresh_tracker_has_zero_counts():
    t = UsageTracker(make_settings(), FakeClock())
    assert await t.remaining("a", False) == 3
    assert await t.remaining("a", True) == 20


async def test_fourth_request_raises_with_reset_seconds():
    clock = FakeClock()  # 12:00 UTC -> 12h to reset
    t = UsageTracker(make_settings(), clock)
    for _ in range(3):
        await use(t, "a")
    assert await t.remaining("a", False) == 0
    with pytest.raises(LimitReached) as ei:
        await t.reserve("a", False)
    assert ei.value.code == "visitor_limit"
    assert ei.value.retry_after_seconds == 12 * 3600
    assert await t.seconds_until_reset() == 12 * 3600


async def test_global_cap_blocks_visitors_not_judges():
    t = UsageTracker(make_settings(cap=2), FakeClock())
    await use(t, "a")
    await use(t, "b")
    with pytest.raises(LimitReached) as ei:
        await t.reserve("c", False)
    assert ei.value.code == "global_cap"
    await use(t, "j", judge=True)  # judge still allowed
    assert await t.remaining("j", True) == 19


async def test_judge_does_not_count_toward_global():
    t = UsageTracker(make_settings(cap=1), FakeClock())
    await use(t, "j", judge=True)
    await use(t, "a")  # global still free


async def test_release_leaves_counts_unchanged():
    t = UsageTracker(make_settings(), FakeClock())
    r = await t.reserve("a", False)
    assert await t.remaining("a", False) == 2  # pending slot is held
    await t.release(r)
    assert await t.remaining("a", False) == 3
    for _ in range(3):
        await use(t, "a")


async def test_commit_counts_once():
    t = UsageTracker(make_settings(), FakeClock())
    r = await t.reserve("a", False)
    await t.commit(r)
    await t.commit(r)
    await t.release(r)
    assert await t.remaining("a", False) == 2


async def test_concurrent_reserves_accept_exactly_limit():
    t = UsageTracker(make_settings(visitor=3), FakeClock())
    results = await asyncio.gather(
        *(t.reserve("a", False) for _ in range(10)), return_exceptions=True
    )
    ok = [r for r in results if not isinstance(r, Exception)]
    assert len(ok) == 3
    assert all(isinstance(r, LimitReached) for r in results if isinstance(r, Exception))


async def test_day_rollover_resets_all_counts():
    clock = FakeClock(datetime(2025, 10, 30, 23, 59, 0, tzinfo=timezone.utc))
    t = UsageTracker(make_settings(cap=3), clock)
    for _ in range(3):
        await use(t, "a")
    await use(t, "j", judge=True)
    stale = await t.reserve("b", True)
    assert await t.seconds_until_reset() == 60
    clock.advance(minutes=2)
    assert await t.remaining("a", False) == 3
    assert await t.remaining("j", True) == 20
    await use(t, "a")  # global cap also reset
    await t.commit(stale)  # stale reservation dropped
    assert await t.remaining("b", True) == 20


async def test_release_after_commit_changes_nothing():
    t = UsageTracker(make_settings(), FakeClock())
    r = await t.reserve("a", False)
    await t.commit(r)
    await t.release(r)
    assert await t.remaining("a", False) == 2


async def test_double_release_does_not_touch_other_reservation():
    t = UsageTracker(make_settings(visitor=2), FakeClock())
    r1 = await t.reserve("a", False)
    r2 = await t.reserve("a", False)
    await t.release(r1)
    await t.release(r1)
    assert await t.remaining("a", False) == 1  # r2 still pending
    await t.commit(r2)
    await t.commit(r2)
    assert await t.remaining("a", False) == 1
    await use(t, "a")
    with pytest.raises(LimitReached):
        await t.reserve("a", False)
