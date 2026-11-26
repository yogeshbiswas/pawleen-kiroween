"""Shrink example PNGs to 512 px wide so pages load fast on mobile."""
from pathlib import Path

from PIL import Image

MAX_WIDTH = 512
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "static" / "examples"


def kb(path: Path) -> float:
    return path.stat().st_size / 1024


for path in sorted(EXAMPLES_DIR.glob("*.png")):
    before = kb(path)
    with Image.open(path) as img:
        # Skip small images: upscaling would only add blur and bytes.
        if img.width <= MAX_WIDTH:
            print(f"{path.name}: {before:.1f} KB (already small, skipped)")
            continue
        height = round(img.height * MAX_WIDTH / img.width)  # keep aspect ratio
        # RGB drops the alpha channel, which makes the PNG smaller.
        small = img.convert("RGB").resize((MAX_WIDTH, height), Image.LANCZOS)
    # Safe to overwrite: the source file is closed and the data is in memory.
    small.save(path, optimize=True)
    print(f"{path.name}: {before:.1f} KB -> {kb(path):.1f} KB")
