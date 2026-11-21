"""Shared pytest fixtures. Kept minimal; later tasks add fakes here."""
import os
import sys

# Make `import app` work no matter where pytest is started from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone


class FakeClock:
    """Mutable clock for day rollover and lockout tests. Call it to get `now`."""

    def __init__(self, now=None):
        self.now = now or datetime(2025, 10, 30, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


# --- Scripted fake agents -------------------------------------------------

import asyncio
import io

import pytest

from app.config import Settings
from app.models import CheckResult, CostumeRequest, GatekeeperDecision

HANG = "hang"


class _ScriptedFake:
    """Plays outcomes in order; the last one repeats. An outcome is a value,
    an exception (raised), or "hang" (never returns until cancelled)."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []

    async def _play(self, call):
        self.calls.append(call)
        index = min(len(self.calls) - 1, len(self.outcomes) - 1)
        outcome = self.outcomes[index]
        if isinstance(outcome, str) and outcome == HANG:
            await asyncio.Event().wait()
        if isinstance(outcome, BaseException) or (
            isinstance(outcome, type) and issubclass(outcome, BaseException)
        ):
            raise outcome
        return outcome


class FakeGatekeeper(_ScriptedFake):
    def __init__(self, *outcomes):
        super().__init__(*(outcomes or (GatekeeperDecision(accepted=True),)))

    async def check(self, req):
        return await self._play((req,))


class FakeCostumeMaker(_ScriptedFake):
    def __init__(self, *outcomes):
        super().__init__(*(outcomes or (fake_png(),)))

    async def make(self, req, scene, failure_reasons):
        return await self._play((req, scene, failure_reasons))


class FakeQualityChecker(_ScriptedFake):
    def __init__(self, *outcomes):
        super().__init__(*(outcomes or (passing_check(),)))

    async def check(self, pet, costumed, costume_text):
        return await self._play((pet, costumed, costume_text))


def passing_check() -> CheckResult:
    return CheckResult(same_pet=True, costume_applied=True, no_cropping=True, reasons=[])


def failing_check(*reasons: str, passed: int = 0) -> CheckResult:
    """A check with `passed` of 3 criteria true (0..2) and the given reasons."""
    flags = [i < passed for i in range(3)]
    return CheckResult(
        same_pet=flags[0],
        costume_applied=flags[1],
        no_cropping=flags[2],
        reasons=list(reasons) or ["failed"],
    )


def test_settings(**overrides) -> Settings:
    values = dict(
        openai_api_key="test-key",
        image_model="test-image-model",
        vision_model="test-vision-model",
        image_quality="medium",
        judge_pass="judge-test-pass-0123456789",
        visitor_daily_limit=3,
        judge_daily_limit=20,
        global_daily_cap=100,
        gatekeeper_timeout=0.05,
        maker_timeout=0.05,
        checker_timeout=0.05,
        pipeline_timeout=0.5,
        heartbeat_interval=0.02,
    )
    values.update(overrides)
    return Settings(**values)


def fake_png(tag: bytes = b"") -> bytes:
    """Tiny valid PNG (1x1). `tag` is appended after IEND so images can be told apart."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"\x00\xff\x00\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
        + tag
    )


def fake_jpeg(tag: bytes = b"") -> bytes:
    """Tiny valid JPEG made with Pillow."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue() + tag


def make_request(**overrides) -> CostumeRequest:
    values = dict(pet=fake_jpeg(), pet_mime="image/jpeg", description="witch costume")
    values.update(overrides)
    return CostumeRequest(**values)


@pytest.fixture(autouse=True)
def forbid_openai_client(monkeypatch):
    """Fail any test that creates a real openai.AsyncOpenAI."""
    try:
        import openai
    except ImportError:
        return

    def _forbidden(*args, **kwargs):
        raise AssertionError("openai.AsyncOpenAI must not be created in tests")

    monkeypatch.setattr(openai, "AsyncOpenAI", _forbidden)
