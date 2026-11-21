import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from app.errors import PawleenError
from app.events import ErrorEvent, HeartbeatEvent, ResultEvent, StepEvent, parse_sse
from app.main import create_app
from app.models import GatekeeperDecision
from app.pipeline import Agents
from tests.conftest import (
    HANG,
    FakeCostumeMaker,
    FakeGatekeeper,
    FakeQualityChecker,
    fake_jpeg,
    fake_png,
    failing_check,
)
from tests.conftest import test_settings as make_settings

PASS = "judge-test-pass-0123456789"


def make_client(gatekeeper=None, maker=None, checker=None, **overrides):
    agents = Agents(
        gatekeeper=gatekeeper or FakeGatekeeper(),
        maker=maker or FakeCostumeMaker(),
        checker=checker or FakeQualityChecker(),
    )
    app = create_app(make_settings(**overrides), agents=agents)
    return TestClient(app), app


def summon(client, description="wizard hat", pet=True, headers=None, costume=None):
    files = {}
    if pet:
        files["pet_photo"] = ("pet.jpg", fake_jpeg(), "image/jpeg")
    if costume:
        files["costume_photo"] = ("c.png", fake_png(), "image/png")
    data = {"description": description} if description is not None else {}
    return client.post("/api/summon", files=files or None, data=data, headers=headers or {})


def remaining(client, headers=None):
    return client.get("/api/usage", headers=headers or {}).json()["remaining"]


def terminal(events):
    return [e for e in events if isinstance(e, (ResultEvent, ErrorEvent))]


def test_success_stream_shape_and_counts():
    client, _ = make_client()
    r = summon(client)
    assert r.status_code == 200
    events = parse_sse(r.text)
    steps = [e.step for e in events if isinstance(e, StepEvent)]
    assert steps == ["gatekeeping", "brewing", "checking"]
    done = terminal(events)
    assert len(done) == 1 and isinstance(done[0], ResultEvent)
    assert events[-1] is done[0]
    assert done[0].remaining == 2 and done[0].limit == 3
    assert done[0].notice is None
    assert base64.b64decode(done[0].image_b64) == fake_png()
    assert remaining(client) == 2


def test_no_buffering_headers():
    client, _ = make_client()
    h = summon(client).headers
    assert h["content-type"].startswith("text/event-stream")
    assert h["cache-control"] == "no-cache, no-transform"
    assert h["x-accel-buffering"] == "no"
    assert h["connection"] == "keep-alive"


def test_fourth_request_returns_429():
    client, _ = make_client()
    for _ in range(3):
        assert summon(client).status_code == 200
    r = summon(client)
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "visitor_limit"
    assert body["retry_after_seconds"] > 0
    assert remaining(client) == 0


def test_global_cap_blocks_visitors():
    client, _ = make_client(global_daily_cap=1)
    assert summon(client).status_code == 200
    other = TestClient(client.app)
    r = summon(other)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "global_cap"
    assert r.json()["error"]["retry_after_seconds"] > 0


def test_judge_pass_raises_limit():
    client, _ = make_client(visitor_daily_limit=1)
    headers = {"X-Judge-Pass": PASS}
    first = parse_sse(summon(client, headers=headers).text)
    assert first[-1].limit == 20 and first[-1].remaining == 19
    assert summon(client, headers=headers).status_code == 200
    # Without the pass, the visitor allowance is separate and untouched.
    assert summon(client).status_code == 200
    assert summon(client).status_code == 429


@pytest.mark.parametrize(
    "kwargs,code",
    [
        (dict(gatekeeper=FakeGatekeeper(GatekeeperDecision(False, "no_animal"))), "no_animal"),
        (dict(gatekeeper=FakeGatekeeper(GatekeeperDecision(False, "bad_costume"))), "bad_costume"),
        (dict(gatekeeper=FakeGatekeeper(HANG)), "gatekeeper_failed"),
        (dict(maker=FakeCostumeMaker(HANG)), "maker_timeout"),
        (dict(maker=FakeCostumeMaker(RuntimeError("x"))), "maker_failed"),
        (dict(maker=FakeCostumeMaker(PawleenError("credits_depleted"))), "credits_depleted"),
        (dict(maker=FakeCostumeMaker(PawleenError("refused"))), "refused"),
    ],
)
def test_every_error_code_leaves_counts_unchanged(kwargs, code):
    client, app = make_client(**kwargs)
    r = summon(client)
    events = parse_sse(r.text)
    done = terminal(events)
    assert len(done) == 1 and isinstance(done[0], ErrorEvent)
    assert done[0].code == code
    assert remaining(client) == 3
    assert app.state.usage._global == 0


def test_bad_costume_shows_chips():
    client, _ = make_client(gatekeeper=FakeGatekeeper(GatekeeperDecision(False, "bad_costume")))
    assert terminal(parse_sse(summon(client).text))[0].show_chips is True


def test_total_timeout_without_image():
    client, _ = make_client(
        maker=FakeCostumeMaker(HANG), maker_timeout=5, pipeline_timeout=0.2
    )
    done = terminal(parse_sse(summon(client).text))
    assert len(done) == 1 and isinstance(done[0], ErrorEvent)
    assert done[0].code == "pipeline_timeout"
    assert remaining(client) == 3


def test_total_timeout_after_image_returns_not_verified_and_counts():
    client, _ = make_client(
        checker=FakeQualityChecker(HANG), checker_timeout=5, pipeline_timeout=0.2
    )
    done = terminal(parse_sse(summon(client).text))
    assert len(done) == 1 and isinstance(done[0], ResultEvent)
    assert done[0].notice == "not_verified"
    assert base64.b64decode(done[0].image_b64) == fake_png()
    assert done[0].remaining == 2
    assert remaining(client) == 2


def test_wonky_result_counts():
    client, _ = make_client(checker=FakeQualityChecker(failing_check("bad", passed=1)))
    done = terminal(parse_sse(summon(client).text))
    assert done[0].notice == "wonky" and done[0].message
    assert remaining(client) == 2


class SlowMaker:
    async def make(self, req, scene, failure_reasons):
        await asyncio.sleep(0.15)
        return fake_png()


def test_heartbeat_while_agent_is_slow():
    client, _ = make_client(maker=SlowMaker(), maker_timeout=2, pipeline_timeout=5)
    events = parse_sse(summon(client).text)
    assert any(isinstance(e, HeartbeatEvent) for e in events)
    assert len(terminal(events)) == 1 and isinstance(events[-1], ResultEvent)


def test_scene_is_passed_to_maker():
    maker = FakeCostumeMaker()
    client, _ = make_client(maker=maker)
    summon(client, description="pirate hat")
    assert maker.calls[0][1] == "a ghost ship on a stormy sea"


def test_costume_photo_only_is_accepted():
    client, _ = make_client()
    assert summon(client, description="", costume=True).status_code == 200


def test_bad_upload_errors_are_free():
    client, _ = make_client()
    r = client.post(
        "/api/summon",
        files={"pet_photo": ("pet.txt", b"hello", "text/plain")},
        data={"description": "hat"},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_upload"
    assert summon(client, pet=False).status_code == 400
    assert summon(client, description="").status_code == 400  # nothing to wear
    assert remaining(client) == 3


def test_error_order_config_then_files_then_reserve():
    client, app = make_client()
    # Exhaust the allowance, then send a bad file: files come before reserve.
    for _ in range(3):
        summon(client)
    assert summon(client, pet=False).json()["error"]["code"] == "bad_upload"
    assert summon(client).json()["error"]["code"] == "visitor_limit"
    # Config problem wins over everything.
    app.state.pipeline_enabled = False
    r = summon(client, pet=False)
    assert r.status_code == 503 and r.json()["error"]["code"] == "config_error"


def test_config_error_keeps_health_working():
    app = create_app(make_settings(openai_api_key=""))
    app.state.pipeline_enabled = False
    client = TestClient(app)
    r = summon(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "config_error"
    assert client.get("/health").json() == {"status": "ok"}


def test_cancelling_the_stream_releases_reservation():
    maker = FakeCostumeMaker(HANG)
    _, app = make_client(maker=maker, maker_timeout=30, pipeline_timeout=60, heartbeat_interval=5)

    boundary = "XBOUNDARY"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="pet_photo"; filename="p.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + fake_jpeg() + (
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="description"\r\n\r\nhat\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/summon",
        "raw_path": b"/api/summon",
        "query_string": b"",
        "headers": [
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("1.2.3.4", 1234),
        "server": ("test", 80),
    }

    async def go():
        disconnect = asyncio.Event()
        sent_body = False
        chunks = []

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"])
                disconnect.set()

        await asyncio.wait_for(app(scope, receive, send), 5)
        assert chunks, "stream never started"
        usage = app.state.usage
        assert not usage._pending_global
        assert usage._global == 0
        assert not usage._pending_visitor

    asyncio.run(go())
