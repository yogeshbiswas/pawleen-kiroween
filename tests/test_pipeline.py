"""Pipeline orchestrator tests, using only scripted fake agents."""
import httpx
import openai

from app.events import StepEvent
from app.models import GatekeeperDecision, PipelineState, Failure, Success
from app.pipeline import Agents, run_pipeline, with_silent_retry
from tests.conftest import (
    HANG,
    FakeCostumeMaker,
    FakeGatekeeper,
    FakeQualityChecker,
    fake_png,
    failing_check,
    make_request,
    passing_check,
)
from tests.conftest import test_settings as make_settings

SCENE = "a foggy pumpkin patch at night"
IMG1 = fake_png(b"one")
IMG2 = fake_png(b"two")


async def run(gk=None, mk=None, qc=None, state=None):
    events = []

    async def emit(ev):
        events.append(ev)

    gk = gk or FakeGatekeeper()
    mk = mk or FakeCostumeMaker(IMG1)
    qc = qc or FakeQualityChecker()
    outcome = await run_pipeline(
        make_request(), Agents(gk, mk, qc), make_settings(), emit, SCENE, state
    )
    return outcome, events, gk, mk, qc


async def test_all_pass():
    outcome, events, gk, mk, qc = await run()
    assert outcome == Success(IMG1, None, None)
    assert len(mk.calls) == 1 and len(qc.calls) == 1
    assert [(e.step, e.attempt, e.recast) for e in events] == [
        ("gatekeeping", 1, False),
        ("brewing", 1, False),
        ("checking", 1, False),
    ]


async def test_one_failed_check_regenerates_once_with_reasons():
    mk = FakeCostumeMaker(IMG1, IMG2)
    qc = FakeQualityChecker(failing_check("hat cut off", passed=2), passing_check())
    outcome, events, _, mk, qc = await run(mk=mk, qc=qc)
    assert outcome == Success(IMG2, None, None)
    assert len(mk.calls) == 2
    assert mk.calls[0][2] is None
    assert mk.calls[1][2] == ["hat cut off"]
    assert mk.calls[1][1] == mk.calls[0][1] == SCENE
    assert [(e.step, e.attempt, e.recast) for e in events[3:]] == [
        ("brewing", 2, True),
        ("checking", 2, True),
    ]


async def test_second_failure_returns_better_image_wonky():
    mk = FakeCostumeMaker(IMG1, IMG2)
    qc = FakeQualityChecker(failing_check("a", passed=1), failing_check("b", passed=2))
    outcome, *_ = await run(mk=mk, qc=qc)
    assert outcome == Success(IMG2, None, "wonky")

    mk = FakeCostumeMaker(IMG1, IMG2)
    qc = FakeQualityChecker(failing_check("a", passed=2), failing_check("b", passed=1))
    outcome, *_ = await run(mk=mk, qc=qc)
    assert outcome == Success(IMG1, None, "wonky")


async def test_checker_fails_twice_on_image_1_not_verified_no_regeneration():
    qc = FakeQualityChecker(RuntimeError("boom"))
    outcome, _, _, mk, qc = await run(qc=qc)
    assert outcome == Success(IMG1, None, "not_verified")
    assert len(mk.calls) == 1 and len(qc.calls) == 2


async def test_checker_timeout_then_success_is_silent():
    qc = FakeQualityChecker(HANG, passing_check())
    outcome, events, _, _, qc = await run(qc=qc)
    assert outcome == Success(IMG1, None, None)
    assert len(qc.calls) == 2
    assert len(events) == 3


async def test_checker_fails_twice_on_image_2_not_verified():
    mk = FakeCostumeMaker(IMG1, IMG2)
    qc = FakeQualityChecker(failing_check("x", passed=2), RuntimeError("boom"))
    outcome, _, _, mk, qc = await run(mk=mk, qc=qc)
    assert outcome == Success(IMG2, None, "not_verified")
    assert len(mk.calls) == 2 and len(qc.calls) == 3


async def test_regeneration_failure_returns_image_1_wonky():
    mk = FakeCostumeMaker(IMG1, RuntimeError("boom"))
    qc = FakeQualityChecker(failing_check("x", passed=2))
    outcome, *_ = await run(mk=mk, qc=qc)
    assert outcome == Success(IMG1, None, "wonky")


async def test_gatekeeper_reject_skips_maker_and_checker():
    gk = FakeGatekeeper(GatekeeperDecision(accepted=False, reason="no_animal"))
    outcome, events, gk, mk, qc = await run(gk=gk)
    assert outcome == Failure("no_animal")
    assert len(gk.calls) == 1 and not mk.calls and not qc.calls
    assert len(events) == 1


async def test_gatekeeper_hang_retried_once_then_failed():
    outcome, _, gk, mk, _ = await run(gk=FakeGatekeeper(HANG))
    assert outcome == Failure("gatekeeper_failed")
    assert len(gk.calls) == 2 and not mk.calls


async def test_gatekeeper_error_then_success_is_silent():
    gk = FakeGatekeeper(RuntimeError("x"), GatekeeperDecision(accepted=True))
    outcome, events, gk, *_ = await run(gk=gk)
    assert isinstance(outcome, Success) and len(gk.calls) == 2
    assert [e.step for e in events].count("gatekeeping") == 1


async def test_maker_hang_is_maker_timeout_after_one_call():
    outcome, _, _, mk, qc = await run(mk=FakeCostumeMaker(HANG))
    assert outcome == Failure("maker_timeout")
    assert len(mk.calls) == 1 and not qc.calls


def _quota_error():
    req = httpx.Request("POST", "https://example.invalid")
    resp = httpx.Response(429, request=req)
    return openai.RateLimitError(
        "x", response=resp, body={"code": "insufficient_quota"}
    )


async def test_credits_error_is_not_retried():
    outcome, _, gk, mk, _ = await run(gk=FakeGatekeeper(_quota_error()))
    assert outcome == Failure("credits_depleted")
    assert len(gk.calls) == 1 and not mk.calls


async def test_best_image_set_as_soon_as_image_exists():
    state = PipelineState()
    seen = []

    class SpyChecker(FakeQualityChecker):
        async def check(self, pet, costumed, costume_text):
            seen.append(state.best_image)
            return await super().check(pet, costumed, costume_text)

    await run(qc=SpyChecker(), state=state)
    assert seen == [IMG1] and state.best_image == IMG1


async def test_costume_name_from_gatekeeper_is_used():
    gk = FakeGatekeeper(GatekeeperDecision(accepted=True, costume_name="Witch costume"))
    outcome, *_ = await run(gk=gk)
    assert outcome.costume_name == "Witch costume"


async def test_with_silent_retry_bounded():
    calls = []

    async def bad():
        calls.append(1)
        raise RuntimeError("x")

    try:
        await with_silent_retry(bad, 1)
    except RuntimeError:
        pass
    assert len(calls) == 2
