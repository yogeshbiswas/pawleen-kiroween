"""Configuration: Settings dataclass and load_settings() validation.

Problem lists and log messages carry variable names only, never values.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)

QUALITY_VALUES = ("low", "medium", "high")
DEFAULT_QUALITY = "medium"
DEFAULT_VISITOR_LIMIT = 3
DEFAULT_JUDGE_LIMIT = 20


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    image_model: str
    vision_model: str
    image_quality: str
    judge_pass: str
    visitor_daily_limit: int
    judge_daily_limit: int
    global_daily_cap: int
    gatekeeper_timeout: float = 30
    maker_timeout: float = 90
    checker_timeout: float = 30
    pipeline_timeout: float = 180
    heartbeat_interval: float = 8


def load_dotenv_file() -> None:
    """Load `.env` into os.environ. Call once at startup, not from load_settings."""
    from dotenv import load_dotenv

    load_dotenv()


def _parse_int(raw: str, low: int, high: int) -> int | None:
    text = raw.strip()
    if not text.isascii() or not text.lstrip("+-").isdigit():
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if low <= value <= high else None


def load_settings(env: Mapping[str, str]) -> tuple[Settings, list[str]]:
    """Return (settings, problem variable names). Never reads .env itself."""
    problems: list[str] = []

    def required_text(name: str) -> str:
        value = (env.get(name) or "").strip()
        if not value:
            problems.append(name)
        return value

    def limit(name: str, default: int | None, low: int, high: int) -> int:
        raw = env.get(name)
        if raw is None or raw.strip() == "":
            if default is None:
                problems.append(name)
                return low
            return default
        value = _parse_int(raw, low, high)
        if value is None:
            problems.append(name)
            return default if default is not None else low
        return value

    api_key = required_text("OPENAI_API_KEY")
    image_model = required_text("OPENAI_IMAGE_MODEL")
    vision_model = required_text("OPENAI_VISION_MODEL")

    quality_raw = env.get("OPENAI_IMAGE_QUALITY")
    if quality_raw is None:
        quality = DEFAULT_QUALITY
    else:
        candidate = quality_raw.strip()
        if candidate in QUALITY_VALUES:
            quality = candidate
        else:
            quality = DEFAULT_QUALITY
            logger.warning("OPENAI_IMAGE_QUALITY is invalid, using %s", DEFAULT_QUALITY)

    judge_pass = env.get("JUDGE_PASS") or ""

    visitor = limit("VISITOR_DAILY_LIMIT", DEFAULT_VISITOR_LIMIT, 1, 1_000_000)
    judge = limit("JUDGE_DAILY_LIMIT", DEFAULT_JUDGE_LIMIT, 1, 1_000_000)
    cap = limit("GLOBAL_DAILY_CAP", None, 1, 100_000)

    settings = Settings(
        openai_api_key=api_key,
        image_model=image_model,
        vision_model=vision_model,
        image_quality=quality,
        judge_pass=judge_pass,
        visitor_daily_limit=visitor,
        judge_daily_limit=judge,
        global_daily_cap=cap,
    )
    return settings, problems
