"""Privacy: photos are closed, never written to disk, and never logged."""
import base64
import logging
import re
import tempfile
from pathlib import Path

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.main import create_app
from app.pipeline import Agents
from tests.conftest import (
    FakeCostumeMaker,
    FakeGatekeeper,
    FakeQualityChecker,
    fake_jpeg,
    fake_png,
)
from tests.conftest import test_settings as make_settings


def make_client(maker=None, **overrides):
    agents = Agents(
        gatekeeper=FakeGatekeeper(),
        maker=maker or FakeCostumeMaker(),
        checker=FakeQualityChecker(),
    )
    return TestClient(create_app(make_settings(**overrides), agents=agents))


@pytest.fixture
def spies(monkeypatch):
    """Record every UploadFile Starlette creates so tests can check they are closed."""
    created = []
    original = UploadFile.__init__

    def spy_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(UploadFile, "__init__", spy_init)
    return created


def post(client, pet=None, costume=None, description="wizard hat"):
    files = {}
    if pet is not None:
        files["pet_photo"] = pet
    if costume is not None:
        files["costume_photo"] = costume
    return client.post("/api/summon", files=files or None, data={"description": description})


def good_pet():
    return ("pet.jpg", fake_jpeg(), "image/jpeg")


def good_costume():
    return ("c.png", fake_png(), "image/png")


def assert_all_closed(spies, expected):
    assert len(spies) == expected
    assert all(u.file.closed for u in spies)


def test_both_photos_closed_after_success(spies):
    r = post(make_client(), good_pet(), good_costume())
    assert r.status_code == 200 and "event: result" in r.text
    assert_all_closed(spies, 2)


def test_both_photos_closed_after_validation_failure(spies):
    bad_costume = ("c.txt", b"hello", "text/plain")
    r = post(make_client(), good_pet(), bad_costume)
    assert r.status_code == 400
    assert_all_closed(spies, 2)


def test_both_photos_closed_after_pipeline_error(spies):
    client = make_client(maker=FakeCostumeMaker(RuntimeError("boom")))
    r = post(client, good_pet(), good_costume())
    assert "event: error" in r.text
    assert_all_closed(spies, 2)


def _temp_listing():
    return sorted(p.name for p in Path(tempfile.gettempdir()).iterdir())


@pytest.mark.parametrize("big", [False, True])
def test_temp_directory_unchanged(spies, big):
    # Above 1 MB Starlette rolls the spooled upload over to a temp file on disk.
    pet_bytes = fake_jpeg() + (b"\0" * (1_200_000) if big else b"")
    client = make_client()
    before = _temp_listing()
    r = post(client, ("pet.jpg", pet_bytes, "image/jpeg"), good_costume())
    assert r.status_code == 200 and "event: result" in r.text
    assert_all_closed(spies, 2)
    assert _temp_listing() == before


def _quota_error():
    req = httpx.Request("POST", "https://example.invalid")
    resp = httpx.Response(429, request=req)
    return openai.RateLimitError("x", response=resp, body={"code": "insufficient_quota"})


def test_debug_logs_hold_no_image_data(caplog):
    pet = fake_jpeg(b"PETTAG")
    out = fake_png(b"OUTTAG")
    client = make_client(maker=FakeCostumeMaker(out))
    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/api/summon",
            files={"pet_photo": ("p.jpg", pet, "image/jpeg")},
            data={"description": "hat"},
        )
    assert "event: result" in r.text
    text = caplog.text
    for blob in (pet, out):
        b64 = base64.b64encode(blob).decode()
        assert b64[:40] not in text
        assert repr(blob)[:30] not in text
    assert "PETTAG" not in text and "OUTTAG" not in text
    assert not re.search(r"[A-Za-z0-9+/]{200,}", text)
    assert "\\x89PNG" not in text and "b'" not in text


def test_credits_depleted_logs_one_entry_without_key(caplog):
    client = make_client(maker=FakeCostumeMaker(_quota_error()))
    with caplog.at_level(logging.DEBUG):
        r = post(client, good_pet())
    assert '"code":"credits_depleted"' in r.text
    hits = [rec for rec in caplog.records if "credits_depleted" in rec.getMessage()]
    assert len(hits) == 1
    assert "test-key" not in caplog.text


WRITE_OPEN = re.compile(r"""\bopen\s*\([^)]*['"][rwax+b]*[wax+][rwax+b]*['"]""")


def test_no_code_path_writes_to_disk():
    offenders = []
    for path in Path(__file__).resolve().parent.parent.joinpath("app").rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if WRITE_OPEN.search(code) or ".write_bytes" in code or ".write_text" in code:
                offenders.append(f"{path.name}:{n}")
    assert offenders == []
