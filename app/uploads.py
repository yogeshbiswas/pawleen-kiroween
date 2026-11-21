"""Upload validation and safe reading of uploaded files."""

from app.errors import PawleenError

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10,485,760
MAX_DESCRIPTION_CHARS = 200


def detect_image_type(data):
    """Return the MIME type implied by the magic bytes, or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(content_type, size, data=None):
    """Raise PawleenError("bad_upload") unless type and size are acceptable.

    When data is given, its magic bytes must match the declared type.
    """
    base = (content_type or "").split(";")[0].strip().lower()
    if base not in ALLOWED_CONTENT_TYPES:
        raise PawleenError("bad_upload")
    if size is None or size <= 0 or size > MAX_UPLOAD_BYTES:
        raise PawleenError("bad_upload")
    if data is not None and detect_image_type(data) != base:
        raise PawleenError("bad_upload")


def trim_description(text):
    """Strip whitespace and cut to 200 characters. None becomes ""."""
    return (text or "").strip()[:MAX_DESCRIPTION_CHARS]


async def read_upload(upload):
    """Validate and read an UploadFile, always closing it. Returns bytes."""
    try:
        # Read one byte past the limit so oversized files are caught without
        # loading the whole thing into memory.
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        validate_upload(upload.content_type, len(data), data)
        return data
    finally:
        await upload.close()
