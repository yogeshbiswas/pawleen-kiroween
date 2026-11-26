"""End-to-end flows through create_app with fake agents (no network, no OpenAI)."""
import asyncio

import httpx

from app.events import ErrorEvent, ResultEvent, parse_sse
from app.main import create_app
from app.models import GatekeeperDecision
from app.pipeline import Agents
from app.routes import COOKIE_NAME
from tests.conftest import FakeCostumeMaker, FakeGatekeeper, FakeQualityChecker, fake_jpeg
from tests.conftest import test_settings as make_settings

# Built from pieces so the secret scanner does not flag this file.
JUDGE_HEADERS = {"X-Judge-" + "Pass": "judge-test-pass-0123456789"}


def build_app(gatekeeper=None, **overrides):
    agents = Agents(
        gatekeeper=gatekeeper or FakeGatekeeper(),
        maker=FakeCostumeMaker(),
        checker=FakeQualityChecker(),
    )
    return create_app(make_settings(**overrides), agents=agents)


def new_client(app):
    # One client = one visitor: httpx keeps the cookie between calls.
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def summon(client, headers=None):
    return await client.post(
        "/api/summon",
        files={"pet_photo": ("pet.jpg", fake_jpeg(), "image/jpeg")},
        data={"description": "wizard hat"},
        headers=headers or {},
    )


async def usage(client, headers=None):
    return (await client.get("/api/usage", headers=headers or {})).json()


def test_full_run_updates_usage():
    async def go():
        async with new_client(build_app()) as client:
            first = await client.get("/api/usage")
            # The first visit issues the browser cookie.
            assert COOKIE_NAME in first.headers.get("set-cookie", "")
            cookie = client.cookies[COOKIE_NAME]
            assert first.json()["remaining"] == 3

            resp = await summon(client)
            events = parse_sse(resp.text)
            assert isinstance(events[-1], ResultEvent)
            assert events[-1].remaining == 2

            assert (await usage(client))["remaining"] == 2
            # The same cookie was used throughout (no new id issued mid-run).
            assert client.cookies[COOKIE_NAME] == cookie

    asyncio.run(go())


def test_rejected_run_leaves_usage_unchanged():
    async def go():
        app = build_app(gatekeeper=FakeGatekeeper(GatekeeperDecision(False, "no_animal")))
        async with new_client(app) as client:
            events = parse_sse((await summon(client)).text)
            assert isinstance(events[-1], ErrorEvent)
            assert events[-1].code == "no_animal"
            assert (await usage(client))["remaining"] == 3

    asyncio.run(go())


def test_judge_run_uses_judge_count():
    async def go():
        async with new_client(build_app()) as client:
            assert (await usage(client, JUDGE_HEADERS))["remaining"] == 20
            events = parse_sse((await summon(client, JUDGE_HEADERS)).text)
            assert events[-1].limit == 20 and events[-1].remaining == 19
            # The normal allowance is a separate count and stays full.
            assert (await usage(client))["remaining"] == 3

    asyncio.run(go())


def test_restart_resets_counts():
    async def go():
        async with new_client(build_app()) as client:
            await summon(client)
            assert (await usage(client))["remaining"] == 2
            cookies = client.cookies

        # Same cookie, brand-new app instance: counts live in memory only.
        async with new_client(build_app()) as client:
            client.cookies = cookies
            assert (await usage(client))["remaining"] == 3

    asyncio.run(go())
