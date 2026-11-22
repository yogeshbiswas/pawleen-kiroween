"""Costume Maker agent: one image-edit call that puts the costume on the pet.

The agent does not retry and has no timeout of its own. The pipeline owns both.
"""
from __future__ import annotations

from app import openai_client
from app.models import CostumeRequest


def build_prompt(
    costume_text: str,
    scene: str,
    failure_reasons: list[str] | None = None,
    has_costume_photo: bool = False,
) -> str:
    """Build the edit prompt. Every rule is spelled out because the image model
    only follows what it is told."""
    lines = [
        "Edit the first image: a photo of a pet. Dress the pet in a Halloween costume.",
        # Keep the same animal, so the owner still recognizes their pet.
        "Preserve the pet's exact appearance: the same species, the same fur or feather "
        "colors, the same markings, and the same facial features.",
        # Portrait output; the app shows it in a tall frame.
        "The picture must be in portrait orientation, with the height greater than the width.",
        # The checker rejects cropped hats, ears and paws.
        "Show the full pet and the full costume, centered, with at least 5% margin on every "
        "side. Do not crop hats, ears, or paws.",
        f"Replace the background with this spooky scene: {scene}",
        # Only the animals get costumes; people stay as they are.
        "Dress only the animals. Do not dress or change any people in the photo.",
    ]
    if costume_text:
        lines.append(f"Costume: {costume_text}")
    if has_costume_photo:
        lines.append(
            "The second image is a costume reference. Copy only the costume (clothing, hat "
            "and accessories) onto the pet. Do not copy any person, face, body, animal or "
            "background from the reference image."
        )
    if failure_reasons:
        lines.append("Fix these problems: " + "; ".join(failure_reasons))
    return "\n".join(lines)


class CostumeMaker:
    def __init__(self, client, settings):
        self.client = client
        self.settings = settings

    async def make(
        self, req: CostumeRequest, scene: str, failure_reasons: list[str] | None
    ) -> bytes:
        """Return PNG bytes. SDK errors and a missing image propagate to the pipeline."""
        images = [(req.pet, req.pet_mime)]
        if req.costume is not None:
            # Costume photo goes second, with its own MIME type.
            images.append((req.costume, req.costume_mime))
        prompt = build_prompt(
            req.costume_text, scene, failure_reasons, has_costume_photo=req.costume is not None
        )
        # edit_image reads quality from settings on every call, including regeneration.
        return await openai_client.edit_image(
            self.client,
            self.settings,
            images=images,
            prompt=prompt,
            timeout=self.settings.maker_timeout,
        )
