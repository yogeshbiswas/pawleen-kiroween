"""Costume Maker tests. The image client is a fake, so no real OpenAI call happens."""
import base64
from types import SimpleNamespace

import pytest

from app.agents.costume_maker import CostumeMaker, build_prompt
from app.errors import PawleenError
from tests.conftest import fake_jpeg, fake_png, make_request, test_settings as make_settings


class FakeImages:
    def __init__(self, result=None, error=None):
        png = base64.b64encode(fake_png()).decode()
        self.result = result or SimpleNamespace(data=[SimpleNamespace(b64_json=png)])
        self.error = error
        self.calls = []

    async def edit(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def maker_with(images, quality="medium"):
    settings = make_settings(image_quality=quality)
    return CostumeMaker(SimpleNamespace(images=images), settings)


def test_prompt_has_every_required_instruction():
    prompt = build_prompt("witch hat", "foggy graveyard").lower()
    for text in (
        "species", "fur or feather colors", "markings", "facial features",
        "portrait orientation", "height greater than the width",
        "full pet", "full costume", "centered", "5% margin",
        "do not crop hats, ears, or paws",
        "replace the background with this spooky scene: foggy graveyard", "dress only the animals", "witch hat",
    ):
        assert text in prompt
    assert "fix these problems" not in prompt
    assert "costume reference" not in prompt


def test_prompt_includes_failure_reasons_on_regeneration():
    prompt = build_prompt("cape", "scene", ["hat cut off", "wrong fur color"])
    assert "Fix these problems: hat cut off; wrong fur color" in prompt


def test_prompt_mentions_costume_photo_only_when_present():
    prompt = build_prompt("", "scene", None, has_costume_photo=True)
    assert (
        "The second image is a costume reference. Copy only the costume (clothing, hat "
        "and accessories) onto the pet. Do not copy any person, face, body, animal or "
        "background from the reference image."
    ) in prompt


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
async def test_quality_reaches_fake_on_first_and_regeneration_call(quality):
    images = FakeImages()
    maker = maker_with(images, quality)
    req = make_request()
    await maker.make(req, "scene", None)
    await maker.make(req, "scene", ["hat cut off"])
    assert [c["quality"] for c in images.calls] == [quality, quality]
    assert "hat cut off" in images.calls[1]["prompt"]


async def test_returns_png_bytes():
    assert await maker_with(FakeImages()).make(make_request(), "scene", None) == fake_png()


async def test_costume_photo_is_sent_as_second_image():
    images = FakeImages()
    pet, costume = fake_jpeg(b"PET"), fake_jpeg(b"COSTUME")
    req = make_request(
        pet=pet, costume=costume, pet_mime="image/png", costume_mime="image/jpeg", description=""
    )
    await maker_with(images).make(req, "scene", None)
    # Each image keeps its own MIME type.
    assert [part[1:] for part in images.calls[0]["image"]] == [
        (pet, "image/png"), (costume, "image/jpeg")
    ]
    assert "costume reference" in images.calls[0]["prompt"]


async def test_only_pet_is_sent_without_costume_photo():
    images = FakeImages()
    await maker_with(images).make(make_request(), "scene", None)
    assert len(images.calls[0]["image"]) == 1


async def test_failed_call_raises():
    maker = maker_with(FakeImages(error=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        await maker.make(make_request(), "scene", None)


async def test_no_image_raises():
    empty = FakeImages(result=SimpleNamespace(data=[]))
    with pytest.raises(PawleenError):
        await maker_with(empty).make(make_request(), "scene", None)
