"""Ready-to-use fake agents for dev runs (USE_FAKE_AGENTS=1). No network, no cost."""
from __future__ import annotations

import asyncio
import io

from app.models import CheckResult, CostumeRequest, GatekeeperDecision


class DevGatekeeper:
    async def check(self, req: CostumeRequest) -> GatekeeperDecision:
        name = None
        if req.costume is not None and not req.description.strip():
            name = "Mystery costume"
        return GatekeeperDecision(accepted=True, reason="ok", costume_name=name)


class DevCostumeMaker:
    def __init__(self, delay: float = 0.5):
        self.delay = delay

    async def make(
        self, req: CostumeRequest, scene: str, failure_reasons: list[str] | None
    ) -> bytes:
        await asyncio.sleep(self.delay)
        return make_placeholder_png()


class DevQualityChecker:
    async def check(self, pet: bytes, costumed: bytes, costume_text: str) -> CheckResult:
        return CheckResult(same_pet=True, costume_applied=True, no_cropping=True, reasons=[])


def make_placeholder_png(width: int = 512, height: int = 768) -> bytes:
    """Portrait placeholder PNG generated with Pillow."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (24, 10, 40))
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        (width * 0.2, height * 0.3, width * 0.8, height * 0.7), fill=(249, 115, 22)
    )
    draw.rectangle((0, height - 40, width, height), fill=(124, 58, 237))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
