import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.errors import PawleenError
from app.uploads import MAX_UPLOAD_BYTES, read_upload, trim_description, validate_upload


@pytest.mark.parametrize("ctype", ["image/jpeg", "image/png", "image/webp"])
def test_valid_types(ctype):
    validate_upload(ctype, 1)


@pytest.mark.parametrize("ctype", ["image/gif", "text/plain", "", None])
def test_wrong_type(ctype):
    with pytest.raises(PawleenError) as e:
        validate_upload(ctype, 100)
    assert e.value.code == "bad_upload"


def test_zero_bytes_rejected():
    with pytest.raises(PawleenError):
        validate_upload("image/png", 0)


def test_exactly_10_mib_accepted():
    assert MAX_UPLOAD_BYTES == 10_485_760
    validate_upload("image/png", MAX_UPLOAD_BYTES)


def test_over_10_mib_rejected():
    with pytest.raises(PawleenError):
        validate_upload("image/png", MAX_UPLOAD_BYTES + 1)


def test_description_trimmed_to_200():
    assert len(trim_description("a" * 500)) == 200
    assert trim_description("  hat  ") == "hat"
    assert trim_description(None) == ""


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def _upload(data=PNG, ctype="image/png"):
    return UploadFile(io.BytesIO(data), headers=Headers({"content-type": ctype}))


async def test_read_upload_returns_bytes_and_closes():
    up = _upload(PNG + b"abc")
    assert await read_upload(up) == PNG + b"abc"
    assert up.file.closed


@pytest.mark.parametrize(
    "data,ctype",
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"),
     (PNG, "IMAGE/PNG; charset=binary")],
)
async def test_real_headers_pass(data, ctype):
    assert await read_upload(_upload(data, ctype)) == data


async def test_text_labelled_png_rejected():
    with pytest.raises(PawleenError) as e:
        await read_upload(_upload(b"hello world, not an image", "image/png"))
    assert e.value.code == "bad_upload"


async def test_png_labelled_jpeg_rejected():
    with pytest.raises(PawleenError) as e:
        await read_upload(_upload(PNG, "image/jpeg"))
    assert e.value.code == "bad_upload"


async def test_closed_when_magic_check_fails():
    up = _upload(b"not an image", "image/png")
    with pytest.raises(PawleenError):
        await read_upload(up)
    assert up.file.closed


async def test_read_upload_closes_when_read_raises():
    up = _upload()

    async def boom(*a, **k):
        raise RuntimeError("fail")

    up.read = boom
    with pytest.raises(RuntimeError):
        await read_upload(up)
    assert up.file.closed


async def test_read_upload_closes_on_invalid():
    up = _upload(b"", "image/png")
    with pytest.raises(PawleenError):
        await read_upload(up)
    assert up.file.closed
