"""Shared OpenAI client and two thin wrappers (call shapes: docs/openai-findings.md).

SDK exceptions are not caught here. Callers map them with classify_openai_error.
Image bytes, base64 and the API key are never logged.
"""
from __future__ import annotations

import base64
import binascii

import openai

from app.errors import PawleenError

# Documented portrait size for the image model (docs/openai-findings.md).
PORTRAIT_SIZE = "1024x1536"
# The app only allows these; the API accepts more (see findings).
ALLOWED_QUALITY = ("low", "medium", "high")


def make_client(settings):
    """Build the one shared client. max_retries=0: the pipeline owns all retries."""
    # Look up openai.AsyncOpenAI at call time so tests can swap it.
    return openai.AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0)


def _has_refusal(response) -> bool:
    """True when any output message holds a refusal item."""
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return True
    return False


async def vision_json(client, settings, *, system, user_text, image_bytes, mime, schema, timeout):
    """Ask the vision model for JSON that fits `schema`; return the parsed model."""
    data_url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")
    response = await client.responses.parse(
        model=settings.vision_model,
        input=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        text_format=schema,
        store=False,  # do not let OpenAI keep the photos
        timeout=timeout,
    )
    parsed = response.output_parsed
    if parsed is None:
        if _has_refusal(response):
            raise PawleenError("refused")
        # Plain exception on purpose: with_silent_retry re-raises PawleenError at once,
        # but retries anything else once (classified as temporary_failure).
        raise RuntimeError("empty vision output")
    return parsed


async def edit_image(client, settings, *, images, prompt, timeout, mime="image/jpeg"):
    """Edit one or two images (pet first, optional costume photo); return PNG bytes."""
    quality = settings.image_quality
    if quality not in ALLOWED_QUALITY:
        quality = "medium"  # config already validates; this is a safety net
    result = await client.images.edit(
        model=settings.image_model,
        image=[(f"image{i}", data, mime) for i, data in enumerate(images, start=1)],
        prompt=prompt,
        size=PORTRAIT_SIZE,
        quality=quality,
        timeout=timeout,
    )
    data = getattr(result, "data", None)
    b64 = getattr(data[0], "b64_json", None) if data else None
    if not b64:
        raise PawleenError("maker_failed")
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise PawleenError("maker_failed") from None
