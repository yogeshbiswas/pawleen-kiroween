"""Costume Maker agent interface. Implemented in task 12.x."""
from __future__ import annotations

from app.models import CostumeRequest


class CostumeMaker:
    async def make(
        self, req: CostumeRequest, scene: str, failure_reasons: list[str] | None
    ) -> bytes:
        """Return PNG bytes."""
        raise NotImplementedError
