"""API routes: /api/usage, /api/judge and /api/summon, plus the Browser_ID dependency."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.datastructures import UploadFile

from app.errors import PawleenError
from app.events import ErrorEvent, HeartbeatEvent, ResultEvent, StepEvent
from app.messages import get_message
from app.models import CostumeRequest, Failure, PipelineState, Success
from app.pipeline import run_pipeline
from app.scenes import choose_scene, get_last_scene, set_last_scene
from app.uploads import read_upload, trim_description
from app.usage import LimitReached

COOKIE_NAME = "browser_id"
COOKIE_MAX_AGE = 365 * 24 * 3600
MAX_ISSUED = 10_000

router = APIRouter()


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return (proto or request.url.scheme) == "https"


def _fallback_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "")
    agent = request.headers.get("user-agent", "")
    digest = hashlib.sha256(f"{ip}|{agent}".encode()).hexdigest()[:16]
    return "anon:" + digest


def get_browser_id(request: Request, response: Response) -> str:
    """Return the Browser_ID, issuing the cookie when missing.

    Without a cookie, the fallback id ("anon:" + hash of first X-Forwarded-For
    entry and user agent) is looked up in a small in-memory map to the token
    issued earlier to that fingerprint. A client that refuses cookies keeps
    getting the same id, and one that accepts the cookie keeps its counts
    from the first request on.
    """
    existing = request.cookies.get(COOKIE_NAME)
    if existing:
        return existing
    issued = request.app.state.issued_ids
    fallback = _fallback_id(request)
    token = issued.get(fallback)
    if token is None:
        if len(issued) >= MAX_ISSUED:
            issued.clear()
        token = issued[fallback] = secrets.token_urlsafe(16)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )
    return token


def _error(code: str, seconds: int | None, status: int, response: Response) -> JSONResponse:
    out = JSONResponse(
        {
            "error": {
                "code": code,
                "message": get_message(code, seconds),
                "retry_after_seconds": seconds,
            }
        },
        status_code=status,
    )
    for cookie in response.headers.getlist("set-cookie"):
        out.headers.append("set-cookie", cookie)
    return out


@router.get("/api/usage")
async def usage(request: Request, browser_id: str = Depends(get_browser_id)):
    state = request.app.state
    is_judge = state.judge.is_valid(request.headers.get("x-judge-pass", ""))
    settings = state.settings
    return {
        "remaining": await state.usage.remaining(browser_id, is_judge),
        "limit": settings.judge_daily_limit if is_judge else settings.visitor_daily_limit,
        "is_judge": is_judge,
        # Why: lets the page hide the judge pass box when judge mode is off.
        "judge_enabled": bool((settings.judge_pass or "").strip()),
        "reset_in_seconds": await state.usage.seconds_until_reset(),
    }


@router.post("/api/judge")
async def judge(request: Request, response: Response, browser_id: str = Depends(get_browser_id)):
    state = request.app.state
    try:
        body = await request.json()
    except Exception:
        body = None
    presented = body.get("pass") if isinstance(body, dict) else None
    if not isinstance(presented, str):
        presented = ""
    result = await state.judge.verify(browser_id, presented)
    if result.locked:
        return _error("judge_locked", result.retry_after_seconds, 429, response)
    if result.valid:
        return {"valid": True, "remaining": await state.usage.remaining(browser_id, True)}
    return {"valid": False}


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
CHIPS_CODES = frozenset({"bad_costume"})


def _is_upload(value) -> bool:
    return isinstance(value, UploadFile)


async def _run_to_queue(req, agents, settings, scene, queue: asyncio.Queue) -> None:
    """Run the pipeline under the total timeout and put the outcome on the queue."""
    state = PipelineState()

    async def emit(event) -> None:
        await queue.put(event)

    try:
        async with asyncio.timeout(settings.pipeline_timeout):
            outcome = await run_pipeline(req, agents, settings, emit, scene, state)
    except TimeoutError:
        if state.best_image is not None:
            outcome = Success(state.best_image, state.costume_name, "not_verified")
        else:
            outcome = Failure("pipeline_timeout")
    except Exception:
        outcome = Failure("temporary_failure")
    await queue.put(outcome)


async def _summon_stream(state, req, scene, reservation, browser_id, is_judge):
    settings = state.settings
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_run_to_queue(req, state.agents, settings, scene, queue))
    committed = False
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), settings.heartbeat_interval)
            except TimeoutError:
                yield HeartbeatEvent(t=int(time.time())).to_sse()
                continue
            if isinstance(item, StepEvent):
                yield item.to_sse()
            elif isinstance(item, Success):
                await state.usage.commit(reservation)
                committed = True
                limit = settings.judge_daily_limit if is_judge else settings.visitor_daily_limit
                yield ResultEvent(
                    image_b64=base64.b64encode(item.image).decode("ascii"),
                    mime="image/png",
                    costume_name=item.costume_name,
                    remaining=await state.usage.remaining(browser_id, is_judge),
                    limit=limit,
                    notice=item.notice,
                    message=get_message(item.notice) if item.notice else None,
                ).to_sse()
                return
            elif isinstance(item, Failure):
                yield ErrorEvent(
                    code=item.error_code,
                    message=get_message(item.error_code),
                    show_chips=item.error_code in CHIPS_CODES,
                ).to_sse()
                return
    finally:
        task.cancel()
        if not committed:
            await asyncio.shield(state.usage.release(reservation))
        req = None  # let the photos be freed


@router.post("/api/summon")
async def summon(request: Request, response: Response, browser_id: str = Depends(get_browser_id)):
    state = request.app.state
    settings = state.settings

    # 1. config
    if not state.pipeline_enabled or state.agents is None:
        return _error("config_error", None, 503, response)

    # 2. files (every upload is closed in the finally block)
    form = None
    try:
        try:
            form = await request.form()
            pet_file = form.get("pet_photo")
            costume_file = form.get("costume_photo")
            if not _is_upload(pet_file):
                raise PawleenError("bad_upload")
            pet = await read_upload(pet_file)
            costume = None
            if _is_upload(costume_file) and (costume_file.filename or ""):
                costume = await read_upload(costume_file)
            description = form.get("description")
            description = trim_description(description if isinstance(description, str) else "")
            pet_mime = pet_file.content_type
            costume_mime = costume_file.content_type if costume is not None else None
        except PawleenError as exc:
            return _error(exc.code, None, 400, response)
        except Exception:
            return _error("bad_upload", None, 400, response)
    finally:
        if form is not None:
            await form.close()

    if costume is None and not description:
        return _error("bad_upload", None, 400, response)

    # 3. reserve
    is_judge = state.judge.is_valid(request.headers.get("x-judge-pass", ""))
    try:
        reservation = await state.usage.reserve(browser_id, is_judge)
    except LimitReached as exc:
        return _error(exc.code, exc.retry_after_seconds, 429, response)

    try:
        req = CostumeRequest(
            pet=pet,
            pet_mime=pet_mime.split(";")[0].strip().lower(),
            costume=costume,
            costume_mime=costume_mime.split(";")[0].strip().lower() if costume_mime else None,
            description=description,
        )
        scene = choose_scene(req.costume_text, get_last_scene(browser_id))
        set_last_scene(browser_id, scene)
    except BaseException:
        await state.usage.release(reservation)
        raise

    out = StreamingResponse(
        _summon_stream(state, req, scene, reservation, browser_id, is_judge),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
    for cookie in response.headers.getlist("set-cookie"):
        out.headers.append("set-cookie", cookie)
    return out
