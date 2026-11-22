"""Manual live smoke test. Run by hand only; it is not part of pytest.

Example:
    .\\.venv\\Scripts\\python scripts/live_smoke.py pet.jpg --description "a grumpy cat" --out result.png

It sends one real POST /api/summon, prints each SSE event name and the final
status, and saves the result PNG. It never prints image data or any key.
"""

import argparse
import base64
import mimetypes
import sys
from pathlib import Path

import httpx

# Allow `python scripts/live_smoke.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events import ErrorEvent, ResultEvent, parse_sse  # noqa: E402


def print_event(event):
    """Print one event as a short line. Image data is never printed."""
    if isinstance(event, ResultEvent):
        # Only safe metadata; image_b64 is deliberately left out.
        print(
            f"event: result (costume={event.costume_name!r}, notice={event.notice}, "
            f"remaining={event.remaining}/{event.limit})"
        )
    elif isinstance(event, ErrorEvent):
        print(f"event: error (code={event.code})")
    else:
        print(f"event: {event.name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send one live summon request.")
    parser.add_argument("pet_photo", help="path to a sample pet image")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--description", default="")
    parser.add_argument("--out", default="live_smoke_result.png", help="where to save the PNG")
    args = parser.parse_args(argv)

    photo = Path(args.pet_photo)
    mime = mimetypes.guess_type(photo.name)[0] or "image/jpeg"
    files = {"pet_photo": (photo.name, photo.read_bytes(), mime)}
    data = {"description": args.description} if args.description else {}

    # Image generation can be slow, so allow a long read timeout.
    with httpx.Client(base_url=args.base_url, timeout=httpx.Timeout(180.0)) as client:
        response = client.post("/api/summon", files=files, data=data)

    events = parse_sse(response.text)
    print(f"http status: {response.status_code}")
    for event in events:
        print_event(event)

    result = next((e for e in events if isinstance(e, ResultEvent)), None)
    if result is None:
        print("final status: no result")
        return 1

    Path(args.out).write_bytes(base64.b64decode(result.image_b64))
    print(f"final status: ok, saved to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
