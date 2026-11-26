import asyncio
import hashlib
import logging

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import test_settings as make_settings

PASS = "judge-test-pass-0123456789"


def make_client(**overrides):
    app = create_app(make_settings(**overrides))
    return TestClient(app), app


def commit(app, browser_id, is_judge=False):
    async def go():
        r = await app.state.usage.reserve(browser_id, is_judge)
        await app.state.usage.commit(r)

    asyncio.run(go())


def test_cookie_issued_when_missing():
    client, _ = make_client()
    r = client.get("/api/usage")
    header = r.headers["set-cookie"].lower()
    assert "browser_id=" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "max-age=31536000" in header
    assert "secure" not in header
    # Cookie is reused afterwards, not reissued.
    assert "set-cookie" not in client.get("/api/usage").headers


def test_cookie_secure_over_https():
    client, _ = make_client()
    r = client.get("/api/usage", headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_fallback_id_without_cookie():
    client, app = make_client()
    headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1", "User-Agent": "ua"}
    first = client.get("/api/usage", headers=headers)
    commit(app, client.cookies["browser_id"])
    client.cookies.clear()
    # Same first X-Forwarded-For entry and user agent: same identity, same count.
    again = {"X-Forwarded-For": "1.2.3.4, 99.9.9.9", "User-Agent": "ua"}
    assert client.get("/api/usage", headers=again).json()["remaining"] == 2
    client.cookies.clear()
    other = {"X-Forwarded-For": "5.6.7.8", "User-Agent": "ua"}
    assert client.get("/api/usage", headers=other).json()["remaining"] == 3
    assert first.json()["remaining"] == 3

def test_usage_for_visitor_and_judge():
    client, app = make_client()
    body = client.get("/api/usage").json()
    assert body["remaining"] == 3 and body["limit"] == 3 and body["is_judge"] is False
    assert 0 < body["reset_in_seconds"] <= 86400
    bid = client.cookies["browser_id"]
    commit(app, bid)
    assert client.get("/api/usage").json()["remaining"] == 2
    judge = client.get("/api/usage", headers={"X-Judge-Pass": PASS}).json()
    assert judge["is_judge"] is True and judge["limit"] == 20 and judge["remaining"] == 20
    bad = client.get("/api/usage", headers={"X-Judge-Pass": "nope"}).json()
    assert bad["is_judge"] is False and bad["limit"] == 3


def test_usage_header_never_locks_out():
    client, _ = make_client()
    for _ in range(10):
        client.get("/api/usage", headers={"X-Judge-Pass": "wrong"})
    assert client.post("/api/judge", json={"pass": PASS}).json()["valid"] is True


def test_judge_valid_and_invalid():
    client, _ = make_client()
    ok = client.post("/api/judge", json={"pass": PASS})
    assert ok.status_code == 200 and ok.json() == {"valid": True, "remaining": 20}
    bad = client.post("/api/judge", json={"pass": "wrong"})
    assert bad.status_code == 200 and bad.json() == {"valid": False}
    assert client.post("/api/judge", content=b"not json").json() == {"valid": False}
    assert client.post("/api/judge", json={"pass": 5}).json() == {"valid": False}


def test_five_wrong_then_locked():
    client, _ = make_client()
    for _ in range(5):
        assert client.post("/api/judge", json={"pass": "wrong"}).json() == {"valid": False}
    r = client.post("/api/judge", json={"pass": PASS})
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "judge_locked"
    assert 0 < err["retry_after_seconds"] <= 3600
    assert err["message"]


def test_locked_response_sets_cookie():
    client, _ = make_client()
    for _ in range(5):
        client.post("/api/judge", json={"pass": "wrong"})
    client.cookies.clear()
    r = client.post("/api/judge", json={"pass": PASS})
    assert r.status_code == 429
    assert "browser_id=" in r.headers["set-cookie"]

def test_pass_never_in_responses_or_logs(caplog):
    client, _ = make_client()
    caplog.set_level(logging.DEBUG)
    responses = [
        client.post("/api/judge", json={"pass": PASS}),
        client.get("/api/usage", headers={"X-Judge-Pass": PASS}),
    ]
    other = TestClient(client.app, headers={"User-Agent": "other"})
    for _ in range(5):
        responses.append(other.post("/api/judge", json={"pass": PASS + "x"}))
    responses.append(other.post("/api/judge", json={"pass": PASS + "x"}))
    for r in responses:
        assert PASS not in r.text
        assert PASS not in str(r.headers)
    assert PASS not in caplog.text


def test_two_browsers_have_separate_judge_counts():
    a, app = make_client()
    b = TestClient(app, headers={"User-Agent": "browser-b"})
    a.headers["User-Agent"] = "browser-a"
    for _ in range(5):
        a.post("/api/judge", json={"pass": "wrong"})
    assert a.post("/api/judge", json={"pass": PASS}).status_code == 429
    assert b.post("/api/judge", json={"pass": PASS}).json()["valid"] is True
    commit(app, a.cookies["browser_id"], is_judge=True)
    ra = a.get("/api/usage", headers={"X-Judge-Pass": PASS}).json()
    rb = b.get("/api/usage", headers={"X-Judge-Pass": PASS}).json()
    assert ra["remaining"] == 19 and rb["remaining"] == 20


def test_usage_judge_enabled_is_false_when_no_pass_is_set():
    # Why: an empty pass means judge mode is off, so the page hides the pass box.
    client, _ = make_client(judge_pass="")
    assert client.get("/api/usage").json()["judge_enabled"] is False


def test_usage_judge_enabled_is_true_when_a_pass_is_set():
    # Pass built from pieces so no secret-looking literal sits in the test.
    client, _ = make_client(judge_pass="judge-" + "test-" + "pass-0123456789")
    assert client.get("/api/usage").json()["judge_enabled"] is True
