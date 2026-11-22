import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, get_host, parse_port
from tests.conftest import test_settings as make_settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("USE_FAKE_AGENTS", raising=False)
    return TestClient(create_app(make_settings()))


def test_health_ok_and_fast(client):
    start = time.monotonic()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert time.monotonic() - start < 1


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Photo Booth" in r.text


def test_unknown_path_is_buried_page(client):
    r = client.get("/nowhere")
    assert r.status_code == 404
    assert "This page has been buried" in r.text
    assert "Photo Booth" not in r.text
    assert 'href="/"' in r.text


def test_missing_static_file_is_buried_page(client):
    r = client.get("/static/nope.css")
    assert r.status_code == 404
    assert "This page has been buried" in r.text


def test_api_unknown_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "error" in r.json()


def test_config_problems_keep_health_and_static_working(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "OPENAI_VISION_MODEL", "GLOBAL_DAILY_CAP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("USE_FAKE_AGENTS", raising=False)
    app = create_app()
    assert app.state.pipeline_enabled is False
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200


def test_fake_agents_off_by_default(client):
    assert client.app.state.agents is None
    assert client.app.state.pipeline_enabled is True


def test_fake_agents_switch_logs_one_warning(monkeypatch, caplog):
    monkeypatch.setenv("USE_FAKE_AGENTS", "1")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        app = create_app(make_settings())
    assert app.state.agents is not None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


@pytest.mark.parametrize("raw,expected", [(None, 8000), ("8080", 8080), ("1", 1), ("65535", 65535)])
def test_parse_port_valid(raw, expected):
    assert parse_port(raw) == expected


@pytest.mark.parametrize("bad", ["abc", "0", "70000"])
def test_invalid_port_exits_nonzero_naming_value(bad):
    env = {**os.environ, "PORT": bad}
    proc = subprocess.run(
        [sys.executable, "-m", "app.main"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 1
    assert bad in proc.stderr


@pytest.mark.parametrize("raw,expected", [(None, "0.0.0.0"), ("", "0.0.0.0"), ("  ", "0.0.0.0"), ("127.0.0.1", "127.0.0.1")])
def test_get_host(raw, expected):
    assert get_host(raw) == expected


@pytest.mark.parametrize("value,expected", [(None, "0.0.0.0"), ("", "0.0.0.0"), ("127.0.0.1", "127.0.0.1")])
def test_main_passes_host_to_uvicorn(monkeypatch, value, expected):
    import uvicorn

    import app.main as main_mod

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: captured.update(kw))
    monkeypatch.setattr(main_mod, "load_dotenv_file", lambda *a, **kw: None)
    monkeypatch.delenv("PORT", raising=False)
    if value is None:
        monkeypatch.delenv("HOST", raising=False)
    else:
        monkeypatch.setenv("HOST", value)
    main_mod.main()
    assert captured["host"] == expected
    assert captured["workers"] == 1


def test_fake_maker_delay_default_and_custom(monkeypatch):
    monkeypatch.setenv("USE_FAKE_AGENTS", "1")
    monkeypatch.delenv("FAKE_MAKER_DELAY_SECONDS", raising=False)
    assert create_app(make_settings()).state.agents.maker.delay == 0.5
    monkeypatch.setenv("FAKE_MAKER_DELAY_SECONDS", "8")
    assert create_app(make_settings()).state.agents.maker.delay == 8


@pytest.mark.parametrize("bad", ["abc", "-1", "nan", "inf", ""])
def test_fake_maker_delay_ignores_invalid_values(monkeypatch, bad):
    monkeypatch.setenv("USE_FAKE_AGENTS", "1")
    monkeypatch.setenv("FAKE_MAKER_DELAY_SECONDS", bad)
    assert create_app(make_settings()).state.agents.maker.delay == 0.5
