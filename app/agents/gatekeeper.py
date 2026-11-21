"""Gatekeeper agent interface. Implemented in task 12.x."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.models import CostumeRequest, GatekeeperDecision


class GatekeeperVerdict(BaseModel):
    has_animal: bool
    description_ok: bool
    costume_photo_ok: bool
    costume_name: str | None = None
    reason: Literal["ok", "no_animal", "bad_costume"]


class Gatekeeper:
    async def check(self, req: CostumeRequest) -> GatekeeperDecision:
        raise NotImplementedError
