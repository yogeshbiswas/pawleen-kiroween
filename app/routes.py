"""API routes: /api/usage and /api/judge, plus the Browser_ID dependency."""
from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.messages import get_message

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
