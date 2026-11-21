"""Data models shared by the pipeline, agents, and routes."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class CostumeRequest:
    pet: bytes
    pet_mime: str
    costume: bytes | None = None
    costume_mime: str | None = None
    description: str = ""  # trimmed, max 200 chars, "" if none
    costume_name: str | None = None  # set from the Gatekeeper for photo-only requests

    @property
    def costume_text(self) -> str:
        """Description if given, else the Gatekeeper's Costume_Name, else empty."""
        desc = (self.description or "").strip()
        if desc:
            return desc
        return (self.costume_name or "").strip()

    def __repr__(self) -> str:
        costume_size = len(self.costume) if self.costume is not None else None
        return (
            f"CostumeRequest(pet_size={len(self.pet)}, "
            f"costume_size={costume_size}, "
            f"description_len={len(self.description or '')})"
        )

    __str__ = __repr__


@dataclass
class PipelineState:
    best_image: bytes | None = None
    costume_name: str | None = None


@dataclass(frozen=True)
class GatekeeperDecision:
    accepted: bool
    reason: str = "ok"  # "ok" | "no_animal" | "bad_costume"
    costume_name: str | None = None


class CheckResult(BaseModel):
    same_pet: bool
    costume_applied: bool
    no_cropping: bool
    reasons: list[str] = []

    @property
    def passed_count(self) -> int:
        return int(self.same_pet) + int(self.costume_applied) + int(self.no_cropping)

    @property
    def all_passed(self) -> bool:
        return self.passed_count == 3


@dataclass(frozen=True)
class Success:
    image: bytes
    costume_name: str | None = None
    notice: str | None = None  # None | "wonky" | "not_verified"

    def __repr__(self) -> str:
        return f"Success(image_size={len(self.image)}, costume_name={self.costume_name!r}, notice={self.notice!r})"


@dataclass(frozen=True)
class Failure:
    error_code: str


PipelineOutcome = Success | Failure
