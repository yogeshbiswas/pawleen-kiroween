"""Quality Checker tests. vision_json is replaced, so no real OpenAI call happens."""
from types import SimpleNamespace

import pytest

from app import openai_client
from app.agents.quality_checker import QualityChecker, QualityVerdict, SYSTEM_PROMPT
from tests.conftest import fake_jpeg, fake_png, test_settings as make_settings

PET = fake_jpeg()
COSTUMED = fake_png(b"costumed")


def verdict(**overrides):
    values = dict(same_pet=True, costume_applied=True, no_cropping=True, reasons=[])
    values.update(overrides)
    return QualityVerdict(**values)


def checker_with(monkeypatch, result, settings=None):
    """Build a QualityChecker whose vision_json returns `result`; calls are recorded."""
    calls = []

    async def fake_vision_json(client, settings, **kwargs):
        calls.append(SimpleNamespace(settings=settings, **kwargs))
        return result

    monkeypatch.setattr(openai_client, "vision_json", fake_vision_json)
    return QualityChecker(client=object(), settings=settings or make_settings()), calls


async def test_all_checks_pass(monkeypatch):
    qc, _ = checker_with(monkeypatch, verdict())
    result = await qc.check(PET, COSTUMED, "witch hat")
    assert result.all_passed is True
    assert result.passed_count == 3
    assert result.reasons == []


@pytest.mark.parametrize("field", ["same_pet", "costume_applied", "no_cropping"])
async def test_single_failure_keeps_its_reason(monkeypatch, field):
    qc, _ = checker_with(monkeypatch, verdict(**{field: False, "reasons": [f"{field} bad"]}))
    result = await qc.check(PET, COSTUMED, "witch hat")
    assert getattr(result, field) is False
    assert result.all_passed is False
    assert result.passed_count == 2
    assert result.reasons == [f"{field} bad"]


async def test_passed_count_with_several_failures(monkeypatch):
    qc, _ = checker_with(monkeypatch, verdict(same_pet=False, no_cropping=False, reasons=["a", "b"]))
    assert (await qc.check(PET, COSTUMED, "x")).passed_count == 1

    qc, _ = checker_with(
        monkeypatch,
        verdict(same_pet=False, costume_applied=False, no_cropping=False, reasons=["a"]),
    )
    assert (await qc.check(PET, COSTUMED, "x")).passed_count == 0


async def test_reasons_are_cleaned(monkeypatch):
    raw = ["  ", " hat cut off ", "b", "c", "d", "x" * 500]
    qc, _ = checker_with(monkeypatch, verdict(no_cropping=False, reasons=raw))
    result = await qc.check(PET, COSTUMED, "x")
    assert result.reasons == ["hat cut off", "b", "c"]


async def test_sends_both_images_and_costume(monkeypatch):
    qc, calls = checker_with(monkeypatch, verdict())
    await qc.check(PET, COSTUMED, "witch hat")
    call = calls[0]
    assert call.image_bytes == PET
    assert call.mime == "image/jpeg"
    assert call.extra_images == [(COSTUMED, "image/png")]
    assert call.schema is QualityVerdict
    assert "witch hat" in call.user_text
    assert call.timeout == qc.settings.checker_timeout


async def test_uses_env_vision_model(monkeypatch):
    settings = make_settings()
    qc, calls = checker_with(monkeypatch, verdict(), settings)
    await qc.check(PET, COSTUMED, "x")
    assert calls[0].settings.vision_model == settings.vision_model


def test_prompt_contains_the_three_rules():
    text = SYSTEM_PROMPT.lower()
    # same species and same primary coat/fur colors
    assert "same species" in text and "coat or fur colors" in text
    # costume visible on the pet
    assert "clearly visible on the pet" in text
    # cropping rule: what fails and what still passes
    for part in ("head", "ears", "hat", "paws", "main costume", "image edge"):
        assert part in text
    assert "tail tip" in text and "cape" in text and "passes" in text
