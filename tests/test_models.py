import pytest

from app.models import CheckResult, CostumeRequest
from tests.conftest import fake_jpeg, fake_png, failing_check, passing_check


def test_costume_text_prefers_description():
    req = CostumeRequest(pet=b"p", pet_mime="image/png", description="  witch ", costume_name="Cape")
    assert req.costume_text == "witch"


def test_costume_text_falls_back_to_costume_name():
    req = CostumeRequest(pet=b"p", pet_mime="image/png", description="", costume_name=" Cape ")
    assert req.costume_text == "Cape"


def test_costume_text_empty_when_nothing():
    assert CostumeRequest(pet=b"p", pet_mime="image/png").costume_text == ""


def test_repr_has_sizes_only():
    secret = b"SECRETBYTES" * 10
    req = CostumeRequest(pet=secret, pet_mime="image/png", costume=b"abc", costume_mime="image/png", description="hi")
    for text in (repr(req), str(req), f"{req}"):
        assert "SECRET" not in text
        assert "b'" not in text
        assert f"pet_size={len(secret)}" in text
        assert "costume_size=3" in text


def test_check_result_counts():
    assert passing_check().all_passed
    assert failing_check("x", passed=2).passed_count == 2
    assert not failing_check("x").all_passed


def test_fake_images_are_valid():
    from PIL import Image
    import io

    assert Image.open(io.BytesIO(fake_png())).format == "PNG"
    assert Image.open(io.BytesIO(fake_jpeg())).format == "JPEG"


async def test_dev_fakes_work():
    from app.fakes import DevCostumeMaker, DevGatekeeper, DevQualityChecker

    from PIL import Image
    import io

    req = CostumeRequest(pet=fake_jpeg(), pet_mime="image/jpeg", description="x")
    assert (await DevGatekeeper().check(req)).accepted
    png = await DevCostumeMaker(delay=0).make(req, "scene", None)
    assert Image.open(io.BytesIO(png)).format == "PNG"
    assert (await DevQualityChecker().check(b"a", png, "x")).all_passed


def test_openai_client_creation_is_blocked():
    openai = pytest.importorskip("openai")
    with pytest.raises(AssertionError):
        openai.AsyncOpenAI(api_key="x")
