"""Static asset checks (first part: Tailwind build files)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_tailwind_css_exists_and_is_not_empty():
    css = ROOT / "static" / "css" / "tailwind.css"
    assert css.is_file()
    assert css.stat().st_size > 0


def test_tailwind_source_files_exist():
    assert (ROOT / "tailwind.config.js").is_file()
    assert (ROOT / "tailwind" / "input.css").is_file()


def test_pytailwindcss_is_dev_only():
    # Why: production (Render) must not install the Tailwind build tool.
    prod = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "pytailwindcss" not in prod
    assert "pytailwindcss" in dev


# ---- Part 2: self-hosted fonts (task 8.2) ----
import re

STATIC = ROOT / "static"
FONTS = STATIC / "fonts"
STYLES = STATIC / "css" / "styles.css"


def test_font_and_license_files_exist():
    for name in (
        "Creepster-Regular.woff2",
        "Inter-Variable.woff2",
        "Creepster-OFL.txt",
        "Inter-OFL.txt",
    ):
        path = FONTS / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name


def test_woff2_files_have_woff2_signature():
    # Why: catches an HTML error page saved under a .woff2 name.
    for name in ("Creepster-Regular.woff2", "Inter-Variable.woff2"):
        assert (FONTS / name).read_bytes()[:4] == b"wOF2", name


def test_license_files_match_their_fonts():
    creepster = (FONTS / "Creepster-OFL.txt").read_text(encoding="utf-8")
    inter = (FONTS / "Inter-OFL.txt").read_text(encoding="utf-8")
    assert "Creepster" in creepster and "Open Font License" in creepster
    assert "Inter" in inter and "Open Font License" in inter


def test_styles_declare_both_fonts_with_swap():
    css = STYLES.read_text(encoding="utf-8")
    blocks = re.findall(r"@font-face\s*\{(.*?)\}", css, flags=re.S)
    assert len(blocks) == 2
    for family in ("Creepster", "Inter"):
        block = next(b for b in blocks if f'"{family}"' in b)
        assert re.search(r"font-display:\s*swap", block)


def test_styles_use_generic_fallbacks_and_regular_headings():
    css = STYLES.read_text(encoding="utf-8")
    assert '"Inter", sans-serif' in css
    assert '"Creepster", serif' in css
    heading = re.search(r"h1,\s*h2,\s*h3\s*\{(.*?)\}", css, flags=re.S)
    assert heading and re.search(r"font-weight:\s*400", heading.group(1))


def test_every_css_url_is_same_origin():
    css = STYLES.read_text(encoding="utf-8")
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css)
    assert urls
    for url in urls:
        # Same-origin means a root-relative path, not "//host" or "scheme:".
        assert url.startswith("/static/"), url
        assert not url.startswith("//"), url


def test_no_cdn_or_font_service_reference_in_static_text_files():
    # Only html/css/js are scanned: the OFL .txt files legitimately contain URLs.
    banned = (
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "unpkg.com",
        "jsdelivr",
        "cdnjs",
        "cdn.",
    )
    scanned = [
        p for p in STATIC.rglob("*") if p.suffix.lower() in {".html", ".css", ".js"}
    ]
    assert scanned
    for path in scanned:
        text = path.read_text(encoding="utf-8").lower()
        for host in banned:
            assert host not in text, f"{host} found in {path.name}"
