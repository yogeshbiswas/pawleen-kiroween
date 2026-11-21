"""App factory, health check, static files, 404 page and the `python -m app.main` entry."""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, load_dotenv_file, load_settings

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DEFAULT_PORT = 8000
DEFAULT_HOST = "0.0.0.0"  # Render needs this; set HOST=127.0.0.1 locally

_FALLBACK_404 = "<!doctype html><title>404</title><p>🪦 This page has been buried...</p>"


def fake_agents_requested(env: Mapping[str, str]) -> bool:
    return (env.get("USE_FAKE_AGENTS") or "").strip() == "1"


def _build_fake_agents():
    from app.fakes import DevCostumeMaker, DevGatekeeper, DevQualityChecker
    from app.pipeline import Agents

    return Agents(gatekeeper=DevGatekeeper(), maker=DevCostumeMaker(), checker=DevQualityChecker())


def create_app(settings: Settings | None = None, agents=None) -> FastAPI:
    """Build the app. With `settings=None`, settings are read from os.environ.

    Config problems never stop the app: `/health` and static files keep working
    and only the pipeline is disabled.
    """
    if settings is None:
        settings, problems = load_settings(os.environ)
        if problems:
            logger.error("Configuration problems: %s", ", ".join(problems))
    else:
        problems = []

    if agents is None and fake_agents_requested(os.environ):
        agents = _build_fake_agents()
        logger.warning("USE_FAKE_AGENTS is on: fake agents are used, no OpenAI calls are made")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.config_problems = problems
    app.state.pipeline_enabled = not problems
    app.state.agents = agents

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
