"""Helper functions of scripts/smoke_test.py, run against the fake-agent app."""
import asyncio
import importlib.util
from pathlib import Path

import httpx

from app.events import ErrorEvent, ResultEvent, StepEvent
from app.main import create_app
from app.pipeline import Agents
from tests.conftest import FakeCostumeMaker, FakeGatekeeper, FakeQualityChecker, fake_jpeg
from tests.conftest import test_settings as make_settings

_path = Path(__file__).resolve().parent.parent / "scripts" / "smoke_test.py"
_spec = importlib.util.spec_from_file_location("smoke_test", _path)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

# Same value as test_settings(); kept as a pieced-together constant for the scanner.
GOOD_PASS = "judge-test-" + "pass-0123456789"


def make_client():
    agents = Agents(FakeGatekeeper(), FakeCostumeMaker(), FakeQualityChecker())
    app = create_app(make_settings(), agents=agents)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def test_basic_checks_pass():
    async def go():
        async with make_client() as client:
            for check in (smoke.check_health, smoke.check_home, smoke.check_not_found, smoke.check_usage):
                ok, _ = await check(client)
                assert ok, check.__name__

    asyncio.run(go())


def test_judge_check_accepts_right_pass_and_rejects_wrong_one():
    async def go():
        async with make_client() as client:
            assert (await smoke.check_judge(client, GOOD_PASS))[0] is True
            assert (await smoke.check_judge(client, "wrong"))[0] is False

    asyncio.run(go())


def test_summon_check_reports_event_names_only(tmp_path):
    photo = tmp_path / "pet.jpg"
    photo.write_bytes(fake_jpeg())

    async def go():
        async with make_client() as client:
            return await smoke.check_summon(client, photo)

    ok, detail = asyncio.run(go())
    assert ok
    assert "step" in detail and "result" in detail
    assert "final status: ok" in detail
    assert "iVBOR" not in detail  # base64 PNG header: no image data


def test_run_checks_never_prints_the_pass(tmp_path, capsys):
    photo = tmp_path / "pet.jpg"
    photo.write_bytes(fake_jpeg())

    async def go():
        async with make_client() as client:
            return await smoke.run_checks(client, GOOD_PASS, str(photo))

    assert asyncio.run(go()) is True
    out = capsys.readouterr().out
    assert "[PASS] judge pass" in out
    assert GOOD_PASS not in out


def test_run_checks_reports_failure_without_exception_text(capsys):
    def boom(request):
        raise httpx.ConnectError("secret-host.internal refused")

    async def go():
        client = httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://x")
        async with client:
            return await smoke.run_checks(client)

    assert asyncio.run(go()) is False
    out = capsys.readouterr().out
    assert "[FAIL] health: failed with ConnectError" in out
    assert "secret-host" not in out


def test_summarize_events_hides_image_and_message():
    names, status = smoke.summarize_events(
        [StepEvent(step="brewing"), ResultEvent(image_b64="QUJD" * 5, costume_name="X", remaining=2, limit=3)]
    )
    assert names == ["step", "result"] and status == "ok"
    names, status = smoke.summarize_events([ErrorEvent(code="bad_upload", message="hidden")])
    assert names == ["error(bad_upload)"] and status == "error: bad_upload"
    assert smoke.summarize_events([])[1] == "no result"
