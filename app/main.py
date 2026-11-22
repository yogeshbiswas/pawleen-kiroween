"""App factory, health check, static files, 404 page and the `python -m app.main` entry."""
from __future__ import annotations

import logging
import math
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, load_dotenv_file, load_settings
from app.judge import JudgeGuard
from app.routes import router as api_router
from app.usage import UsageTracker

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DEFAULT_PORT = 8000
DEFAULT_HOST = "0.0.0.0"  # Render needs this; set HOST=127.0.0.1 locally

_FALLBACK_404 = "<!doctype html><title>404</title><p>🪦 This page has been buried...</p>"


def fake_agents_requested(env: Mapping[str, str]) -> bool:
    return (env.get("USE_FAKE_AGENTS") or "").strip() == "1"


DEFAULT_FAKE_MAKER_DELAY = 0.5


def fake_maker_delay(env: Mapping[str, str]) -> float:
    """Dev-only delay for the fake Costume Maker. Invalid values keep the default."""
    raw = (env.get("FAKE_MAKER_DELAY_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_FAKE_MAKER_DELAY
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    # nan and inf pass float() but are not usable delays.
    if not math.isfinite(value) or value < 0:
        logger.warning("FAKE_MAKER_DELAY_SECONDS is invalid, using %s", DEFAULT_FAKE_MAKER_DELAY)
        return DEFAULT_FAKE_MAKER_DELAY
    return value


def _build_fake_agents(env: Mapping[str, str]):
    from app.fakes import DevCostumeMaker, DevGatekeeper, DevQualityChecker
    from app.pipeline import Agents

    maker = DevCostumeMaker(delay=fake_maker_delay(env))
    return Agents(gatekeeper=DevGatekeeper(), maker=maker, checker=DevQualityChecker())


def _build_real_agents(settings: Settings):
    from app import openai_client
    from app.agents.costume_maker import CostumeMaker
    from app.agents.gatekeeper import Gatekeeper
    from app.agents.quality_checker import QualityChecker
    from app.pipeline import Agents

    # One shared client for all three agents.
    client = openai_client.make_client(settings)
    return Agents(
        gatekeeper=Gatekeeper(client, settings),
        maker=CostumeMaker(client, settings),
        checker=QualityChecker(client, settings),
    )


def create_app(settings: Settings | None = None, agents=None) -> FastAPI:
    """Build the app. With `settings=None`, settings are read from os.environ.

    Config problems never stop the app: `/health` and static files keep working
    and only the pipeline is disabled.
    """
    # Real agents are built only from environment settings. Tests that pass
    # `settings` or `agents` themselves never reach OpenAI.
    from_env = settings is None
    if from_env:
        settings, problems = load_settings(os.environ)
        if problems:
            logger.error("Configuration problems: %s", ", ".join(problems))
    else:
        problems = []

    if agents is None and fake_agents_requested(os.environ):
        agents = _build_fake_agents(os.environ)
        logger.warning("USE_FAKE_AGENTS is on: fake agents are used, no OpenAI calls are made")
    elif agents is None and from_env and not problems:
        agents = _build_real_agents(settings)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.config_problems = problems
    app.state.pipeline_enabled = not problems
    app.state.agents = agents
    app.state.usage = UsageTracker(settings)
    app.state.judge = JudgeGuard(settings)
    app.state.issued_ids = {}
    app.include_router(api_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            path = request.url.path
            if path == "/api" or path.startswith("/api/"):
                return JSONResponse(
                    {"error": {"code": "not_found", "message": "Nothing lurks here."}},
                    status_code=404,
                )
            page = STATIC_DIR / "404.html"
            if page.is_file():
                return FileResponse(page, status_code=404, media_type="text/html")
            return Response(_FALLBACK_404, status_code=404, media_type="text/html")
        return JSONResponse(
            {"error": {"code": "http_error", "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
    return app


def parse_port(raw: str | None) -> int | None:
    """Return the port, or None when `raw` is not an integer from 1 to 65535."""
    if raw is None:
        return DEFAULT_PORT
    text = raw.strip()
    if not text.isascii() or not text.isdigit():
        return None
    value = int(text)
    return value if 1 <= value <= 65535 else None


def get_host(raw: str | None = None) -> str:
    """Bind address from `raw` (the HOST value); empty or unset means DEFAULT_HOST."""
    text = (raw or "").strip()
    return text or DEFAULT_HOST


def main() -> None:
    load_dotenv_file()
    host = get_host(os.environ.get("HOST"))
    raw = os.environ.get("PORT")
    port = parse_port(raw)
    if port is None:
        print(f"Invalid PORT value {raw!r}: expected an integer from 1 to 65535", file=sys.stderr)
        sys.exit(1)

    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=host, port=port, workers=1)


if __name__ == "__main__":
    main()
