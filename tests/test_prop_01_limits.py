# Feature: pawleen-photo-booth, Property 1: Limits are never exceeded
"""**Validates: Requirements 10.1, 10.2, 10.6, 10.7, 10.16**"""
import asyncio
from collections import Counter

from hypothesis import HealthCheck, given, settings as hsettings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from app.config import Settings
from app.usage import LimitReached, UsageTracker
from tests.conftest import FakeClock

PBT = hsettings(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))
BROWSERS = ["a", "b", "c"]


def make_settings(visitor, judge, cap):
    return Settings(
        openai_api_key="k", image_model="m", vision_model="v", image_quality="medium",
        judge_pass="", visitor_daily_limit=visitor, judge_daily_limit=judge,
        global_daily_cap=cap,
    )  # fmt: skip


limits = st.tuples(st.integers(1, 5), st.integers(1, 8), st.integers(1, 12))
ops = st.lists(
    st.tuples(
        st.sampled_from(["reserve", "commit", "release"]),
        st.sampled_from(BROWSERS),
        st.booleans(),
        st.integers(0, 50),
    ),
    max_size=60,
)


@PBT
@given(limits=limits, ops=ops)
def test_sequential_ops_never_exceed_limits(limits, ops):
    visitor, judge, cap = limits

    async def run():
        t = UsageTracker(make_settings(visitor, judge, cap), FakeClock())
        held = []  # outstanding reservations
        used = Counter()  # (browser, is_judge) -> committed + pending
        glob = 0
        for action, bid, is_judge, pick in ops:
            if action == "reserve":
                limit = judge if is_judge else visitor
                try:
                    r = await t.reserve(bid, is_judge)
                except LimitReached as e:
                    assert e.code in ("visitor_limit", "global_cap")
                    assert e.retry_after_seconds > 0
                    # Rejected only because a limit was truly hit.
                    assert used[(bid, is_judge)] >= limit or (
                        not is_judge and glob >= cap
                    )
                else:
                    held.append(r)
                    used[(bid, is_judge)] += 1
                    glob += 0 if is_judge else 1
            elif held:
                r = held.pop(pick % len(held))
                if action == "commit":
                    await t.commit(r)
                else:
                    await t.release(r)
                    used[(r.browser_id, r.is_judge)] -= 1
                    glob -= 0 if r.is_judge else 1
            for (b, j), n in used.items():
                assert n <= (judge if j else visitor)
                assert await t.remaining(b, j) == (judge if j else visitor) - n
            assert glob <= cap

    asyncio.run(run())


@PBT
@given(limits=limits, n=st.integers(1, 30), is_judge=st.booleans())
def test_concurrent_reserves_single_browser_accept_at_most_limit(limits, n, is_judge):
    visitor, judge, cap = limits

    async def run():
        t = UsageTracker(make_settings(visitor, judge, cap), FakeClock())
        results = await asyncio.gather(
            *(t.reserve("a", is_judge) for _ in range(n)), return_exceptions=True
        )
        ok = [r for r in results if not isinstance(r, Exception)]
        bad = [r for r in results if isinstance(r, Exception)]
        assert all(isinstance(e, LimitReached) for e in bad)
        limit = judge if is_judge else visitor
        if is_judge:
            assert len(ok) == min(n, limit)
        else:
            assert len(ok) == min(n, limit, cap)
        assert await t.remaining("a", is_judge) == max(0, limit - len(ok))

    asyncio.run(run())


@PBT
@given(
    limits=limits,
    reqs=st.lists(st.tuples(st.sampled_from(BROWSERS), st.booleans()), min_size=1, max_size=40),
)
def test_concurrent_reserves_mixed_browsers_respect_all_limits(limits, reqs):
    visitor, judge, cap = limits

    async def run():
        t = UsageTracker(make_settings(visitor, judge, cap), FakeClock())
        results = await asyncio.gather(
            *(t.reserve(b, j) for b, j in reqs), return_exceptions=True
        )
        per = Counter()
        glob = 0
        for (b, j), r in zip(reqs, results):
            if isinstance(r, Exception):
                assert isinstance(r, LimitReached)
            else:
                per[(b, j)] += 1
                glob += 0 if j else 1
        for (b, j), n in per.items():
            assert n <= (judge if j else visitor)
        assert glob <= cap

    asyncio.run(run())


class UsageMachine(RuleBasedStateMachine):
    VISITOR, JUDGE, CAP = 3, 4, 5

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.clock = FakeClock()
        self.tracker = UsageTracker(
            make_settings(self.VISITOR, self.JUDGE, self.CAP), self.clock
        )
        self.held = []
        self.used = Counter()
        self.glob = 0

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def teardown(self):
        self.loop.close()

    @rule(bid=st.sampled_from(BROWSERS), judge=st.booleans())
    def reserve(self, bid, judge):
        limit = self.JUDGE if judge else self.VISITOR
        try:
            r = self.run(self.tracker.reserve(bid, judge))
        except LimitReached:
            assert self.used[(bid, judge)] >= limit or (
                not judge and self.glob >= self.CAP
            )
            return
        self.held.append(r)
        self.used[(bid, judge)] += 1
        self.glob += 0 if judge else 1

    @precondition(lambda self: self.held)
    @rule(data=st.data())
    def commit(self, data):
        r = self.held.pop(data.draw(st.integers(0, len(self.held) - 1)))
        self.run(self.tracker.commit(r))

    @precondition(lambda self: self.held)
    @rule(data=st.data())
    def release(self, data):
        r = self.held.pop(data.draw(st.integers(0, len(self.held) - 1)))
        self.run(self.tracker.release(r))
        self.used[(r.browser_id, r.is_judge)] -= 1
        self.glob -= 0 if r.is_judge else 1

    @invariant()
    def limits_hold(self):
        for (b, j), n in self.used.items():
            limit = self.JUDGE if j else self.VISITOR
            assert n <= limit
            assert self.run(self.tracker.remaining(b, j)) == limit - n
        assert self.glob <= self.CAP
        assert 1 <= self.run(self.tracker.seconds_until_reset()) <= 86400


TestUsageMachine = UsageMachine.TestCase
TestUsageMachine.settings = hsettings(
    max_examples=100, stateful_step_count=30, deadline=None,
    suppress_health_check=list(HealthCheck),
)
