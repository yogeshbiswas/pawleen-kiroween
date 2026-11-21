"""Quality Checker agent interface. Implemented in task 12.x."""
from __future__ import annotations

from app.models import CheckResult

__all__ = ["CheckResult", "QualityChecker"]


class QualityChecker:
    async def check(self, pet: bytes, costumed: bytes, costume_text: str) -> CheckResult:
        raise NotImplementedError
