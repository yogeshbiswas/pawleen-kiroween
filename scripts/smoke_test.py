"""Post-deploy smoke test. Run it by hand against a deployed (or local) Pawleen.

Examples:
    .\\.venv\\Scripts\\python scripts/smoke_test.py https://your-app.onrender.com
    .\\.venv\\Scripts\\python scripts/smoke_test.py http://localhost:8000 --judge-pass "..." --summon sample.jpg

The judge pass can also come from the SMOKE_JUDGE_PASS environment variable, so it
stays out of your shell history. The pass is never printed. A summon uses one real
image from the daily limit, so it only runs when you ask with --summon.
Exit code 0 means every check passed.
"""

import argparse
import asyncio
import mimetypes
import os
import sys
from pathlib import Path

import httpx

# Allow `python scripts/smoke_test.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events import ErrorEvent, ResultEvent, parse_sse  # noqa: E402

JUDGE_HEADER = "X-Judge-" + "Pass"
# An unknown path that should show the "buried" 404 page.
MISSING_PATH = "/smoke-test-no-such-page"


# Each check returns (ok, detail). The detail never contains the judge pass.


async def check_health(client):
    r = await client.get("/health")
    ok = r.status_code == 200 and r.json().get("status") == "ok"
    return ok, f"status {r.status_code}"


async def check_home(client):
    r = await client.get("/")
    ok = r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
    return ok, f"status {r.status_code}"


async def check_not_found(client):
    r = await client.get(MISSING_PATH)
    # The 404 page must be the buried page, not the booth page with status 200.
    ok = r.status_code == 404 and "buried" in r.text
    return ok, f"status {r.status_code}"


async def check_usage(client, judge_pass=None):
    headers = {JUDGE_HEADER: judge_pass} if judge_pass else {}
    r = await client.get("/api/usage", headers=headers)
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and "remaining" in body and "limit" in body
    return ok, f"status {r.status_code}, remaining {body.get('remaining')}/{body.get('limit')}"


async def check_judge(client, judge_pass):
    r = await client.post("/api/judge", json={"pass": judge_pass})
    body = r.json() if r.status_code == 200 else {}
    return body.get("valid") is True, f"status {r.status_code}, valid={body.get('valid')}"


def summarize_events(events):
    """Return (event names, final status). Image data and error text are left out."""
    names = []
    for event in events:
        if isinstance(event, ErrorEvent):
            names.append(f"error({event.code})")
        else:
            names.append(event.name)
    last = events[-1] if events else None
    if isinstance(last, ResultEvent):
        return names, "ok"
    if isinstance(last, ErrorEvent):
        return names, f"error: {last.code}"
    return names, "no result"


async def check_summon(client, photo_path, judge_pass=None):
    photo = Path(photo_path)
    mime = mimetypes.guess_type(photo.name)[0] or "image/jpeg"
    files = {"pet_photo": (photo.name, photo.read_bytes(), mime)}
    headers = {JUDGE_HEADER: judge_pass} if judge_pass else {}
    data = {"description": "wizard hat"}
    async with client.stream("POST", "/api/summon", files=files, data=data, headers=headers) as r:
        await r.aread()
    if r.status_code != 200:
        return False, f"status {r.status_code}"
    names, status = summarize_events(parse_sse(r.text))
    return status == "ok", f"events: {', '.join(names)}; final status: {status}"


async def run_checks(client, judge_pass=None, summon_photo=None):
    """Run every check and print one line each. Returns True when all passed."""
    checks = [
        ("health", check_health(client)),
        ("home page", check_home(client)),
        ("404 page", check_not_found(client)),
        ("usage", check_usage(client, judge_pass)),
    ]
    if judge_pass:
        checks.append(("judge pass", check_judge(client, judge_pass)))
    if summon_photo:
        checks.append(("summon", check_summon(client, summon_photo, judge_pass)))

    all_ok = True
    for name, coro in checks:
        try:
            ok, detail = await coro
        except Exception as exc:
            # Type only: the message could hold a URL or other details.
            ok, detail = False, f"failed with {type(exc).__name__}"
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return all_ok


async def _run(args, judge_pass):
    # Summons can be slow, so allow a long read timeout.
    async with httpx.AsyncClient(base_url=args.base_url, timeout=httpx.Timeout(180.0)) as client:
        return await run_checks(client, judge_pass, args.summon)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Post-deploy smoke test for Pawleen.")
    parser.add_argument("base_url", help="for example https://your-app.onrender.com")
    parser.add_argument("--judge-pass", default=None, help="or set SMOKE_JUDGE_PASS")
    parser.add_argument("--summon", metavar="SAMPLE.JPG", help="also run one real summon")
    args = parser.parse_args(argv)

    judge_pass = args.judge_pass or os.environ.get("SMOKE_JUDGE_" + "PASS") or None
    ok = asyncio.run(_run(args, judge_pass))
    print("smoke test: " + ("all checks passed" if ok else "some checks failed"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
