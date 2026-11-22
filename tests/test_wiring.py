"""create_app picks real agents, fake agents, or no agents (task 12.7)."""
from unittest.mock import MagicMock

import openai
import pytest
from fastapi.testclient import TestClient

from app.agents.costume_maker import CostumeMaker
from app.agents.gatekeeper import Gatekeeper
from app.agents.quality_checker import QualityChecker
from app.fakes import DevCostumeMaker, DevGatekeeper, DevQualityChecker
from app.main import create_app

ENV_NAMES = [
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_MODEL",
    "OPENAI_VISION_MODEL",
    "GLOBAL_DAILY_CAP",
    "USE_FAKE_AGENTS",
]


@pytest.fixture
def valid_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "test-image-model")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "test-vision-model")
    monkeypatch.setenv("GLOBAL_DAILY_CAP", "50")
    return monkeypatch


def test_valid_config_builds_real_agents_with_one_shared_client(valid_env):
    factory = MagicMock(name="AsyncOpenAI")
    valid_env.setattr(openai, "AsyncOpenAI", factory)

    app = create_app()

    agents = app.state.agents
    assert isinstance(agents.gatekeeper, Gatekeeper)
    assert isinstance(agents.maker, CostumeMaker)
    assert isinstance(agents.checker, QualityChecker)
    factory.assert_called_once()
    assert agents.gatekeeper.client is agents.maker.client is agents.checker.client
    assert app.state.pipeline_enabled is True


def test_fake_flag_builds_fake_agents_without_a_client(valid_env):
    valid_env.setenv("USE_FAKE_AGENTS", "1")

    # The autouse fixture makes AsyncOpenAI raise, so this also proves no client is built.
    app = create_app()

    agents = app.state.agents
    assert isinstance(agents.gatekeeper, DevGatekeeper)
    assert isinstance(agents.maker, DevCostumeMaker)
    assert isinstance(agents.checker, DevQualityChecker)


def test_config_problem_disables_pipeline_and_summon_returns_config_error(valid_env):
    valid_env.delenv("OPENAI_API_KEY")

    app = create_app()

    assert app.state.agents is None
    assert app.state.pipeline_enabled is False
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    response = client.post("/api/summon")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "config_error"


def test_agents_argument_still_wins(valid_env):
    marker = object()

    app = create_app(agents=marker)

    assert app.state.agents is marker
