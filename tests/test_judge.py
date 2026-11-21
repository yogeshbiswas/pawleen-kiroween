import logging

from app.config import Settings
from app.judge import JudgeGuard
from tests.conftest import FakeClock

PASS = "s3cret-pass"


def make_guard(judge_pass=PASS):
    s = Settings(
        openai_api_key="k", image_model="m", vision_model="v", image_quality="medium",
        judge_pass=judge_pass, visitor_daily_limit=3, judge_daily_limit=20,
        global_daily_cap=100,
    )  # fmt: skip
    clock = FakeClock()
    return JudgeGuard(s, clock), clock


def test_is_valid_correct_and_wrong():
    g, _ = make_guard()
    assert g.is_valid(PASS)
    assert not g.is_valid("nope")
    assert not g.is_valid("")
    assert not g.is_valid(PASS + "x" * 200)


def test_empty_configured_pass_rejects_everything():
    g, _ = make_guard("")
    assert not g.is_valid("")
    assert not g.is_valid("anything")


async def test_verify_correct_and_wrong():
    g, _ = make_guard()
    assert (await g.verify("a", PASS)).status == "valid"
    assert (await g.verify("a", "bad")).status == "invalid"


async def test_five_wrong_lock_and_sixth_correct_is_locked():
    g, clock = make_guard()
    for _ in range(5):
        assert (await g.verify("a", "bad")).status == "invalid"
    r = await g.verify("a", PASS)
    assert r.status == "locked"
    assert r.retry_after_seconds == 3600
    clock.advance(seconds=100)
    assert (await g.verify("a", PASS)).retry_after_seconds == 3500


async def test_lock_expires_after_one_hour_and_resets_count():
    g, clock = make_guard()
    for _ in range(5):
        await g.verify("a", "bad")
    clock.advance(hours=1)
    assert (await g.verify("a", PASS)).status == "valid"
    for _ in range(4):
        assert (await g.verify("a", "bad")).status == "invalid"
    assert (await g.verify("a", PASS)).status == "valid"


async def test_browsers_locked_separately():
    g, _ = make_guard()
    for _ in range(5):
        await g.verify("a", "bad")
    assert (await g.verify("a", PASS)).status == "locked"
    assert (await g.verify("b", PASS)).status == "valid"


async def test_pass_never_logged(caplog):
    g, _ = make_guard()
    with caplog.at_level(logging.DEBUG):
        for _ in range(6):
            await g.verify("a", "wrong-value")
        await g.verify("b", PASS)
    assert PASS not in caplog.text
    assert "wrong-value" not in caplog.text


def test_presented_pass_with_surrounding_whitespace_is_accepted():
    g, _ = make_guard()
    assert g.is_valid("  " + PASS + "\n")
    assert g.is_valid(PASS + " ")


def test_whitespace_only_presented_pass_is_invalid():
    g, _ = make_guard()
    assert not g.is_valid("   ")
    assert not g.is_valid("\n\t")


def test_length_limit_applies_to_trimmed_value():
    g, _ = make_guard("x" * 128)
    assert g.is_valid("  " + "x" * 128 + "  ")
    g2, _ = make_guard("x" * 129)
    assert not g2.is_valid("x" * 129)


def test_whitespace_only_configured_pass_rejects_everything():
    g, _ = make_guard("  \n ")
    assert not g.is_valid("")
    assert not g.is_valid("   ")
    assert not g.is_valid("anything")


async def test_verify_accepts_whitespace_padded_pass():
    g, _ = make_guard()
    assert (await g.verify("a", f" {PASS}\n")).status == "valid"
