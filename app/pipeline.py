"""Pipeline orchestrator: the only place that calls the agents in order.

Agents raise on failure and know nothing about timeouts or retries. This module
applies the timeouts, the silent-retry policy and the regeneration rule.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.errors import PawleenError, classify_openai_error
from app.events import StepEvent
from app.models import (
    CheckResult,
    CostumeRequest,
    Failure,
    PipelineOutcome,
    PipelineState,
    Success,
)

# Errors that a retry cannot fix (and that must not cost a second call).
NON_RETRIABLE = frozenset({"credits_depleted", "refused", "config_error"})


@dataclass
class Agents:
    gatekeeper: Any
    maker: Any
    checker: Any


async def with_silent_retry(call: Callable[[], Awaitable[Any]], timeout: float):
    """Run `call` with a timeout; on a retriable failure try once more, silently.

    Credit and safety errors (and any PawleenError) are raised at once as
    PawleenError. After the second failure the last error is raised.
    """
    for attempt in (1, 2):
        try:
            async with asyncio.timeout(timeout):
                return await call()
        except TimeoutError:
            if attempt == 2:
                raise
        except PawleenError as exc:
            raise exc
        except Exception as exc:
            code = classify_openai_error(exc)
            if code in NON_RETRIABLE:
                raise PawleenError(code) from None
            if attempt == 2:
                raise


def _step(step: str, attempt: int = 1) -> StepEvent:
    return StepEvent(step=step, attempt=attempt, max_attempts=2, recast=attempt == 2)


async def _check_or_none(agents: Agents, req: CostumeRequest, image: bytes, timeout: float):
    """Quality check with one silent retry. None means 'could not verify'."""
    try:
        return await with_silent_retry(
            lambda: agents.checker.check(req.pet, image, req.costume_text), timeout
        )
    except Exception:
        return None


async def run_pipeline(
    req: CostumeRequest,
    agents: Agents,
    settings: Settings,
    emit: Callable[[Any], Awaitable[None]],
    scene: str,
    state: PipelineState | None = None,
) -> PipelineOutcome:
    state = state if state is not None else PipelineState()

    # 1. Gatekeeper
    await emit(_step("gatekeeping"))
    try:
        decision = await with_silent_retry(
            lambda: agents.gatekeeper.check(req), settings.gatekeeper_timeout
        )
    except PawleenError as exc:
        return Failure(exc.code)
    except Exception:
        return Failure("gatekeeper_failed")
    if not decision.accepted:
        return Failure(decision.reason if decision.reason != "ok" else "bad_costume")
    if decision.costume_name:
        req.costume_name = decision.costume_name
        state.costume_name = decision.costume_name
    name = state.costume_name

    # 2. First image: no retry on timeout
    await emit(_step("brewing"))
    try:
        async with asyncio.timeout(settings.maker_timeout):
            image1 = await agents.maker.make(req, scene, None)
    except TimeoutError:
        return Failure("maker_timeout")
    except Exception as exc:
        code = classify_openai_error(exc)
        return Failure("maker_failed" if code == "temporary_failure" else code)
    state.best_image = image1

    # 3. Check image 1
    await emit(_step("checking"))
    r1 = await _check_or_none(agents, req, image1, settings.checker_timeout)
    if r1 is None:
        return Success(image1, name, "not_verified")
    if r1.all_passed:
        return Success(image1, name)

    # 4. One regeneration with the failure reasons and the same scene
    await emit(_step("brewing", attempt=2))
    try:
        async with asyncio.timeout(settings.maker_timeout):
            image2 = await agents.maker.make(req, scene, list(r1.reasons))
    except Exception:
        return Success(image1, name, "wonky")
    state.best_image = image2

    await emit(_step("checking", attempt=2))
    r2 = await _check_or_none(agents, req, image2, settings.checker_timeout)
    if r2 is None:
        return Success(image2, name, "not_verified")
    if r2.all_passed:
        return Success(image2, name)

    best = image2 if r2.passed_count >= r1.passed_count else image1
    state.best_image = best
    return Success(best, name, "wonky")
