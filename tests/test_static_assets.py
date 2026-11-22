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


# ---- Part 3: page skeleton (task 8.3) ----
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import test_settings as make_settings

FOOTER_TEXT = (
    "🔒 Your photos are only used to create your costume (processed by OpenAI) "
    "and are never stored on our servers. Your gallery stays in your browser."
)
PAGES = [STATIC / "index.html", STATIC / "404.html"]


def test_pages_have_no_external_urls():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        # Why: any http(s) URL would be a request to another origin.
        assert not re.search(r"https?://", text), page.name
        assert "//cdn" not in text and "tailwindcss.com" not in text, page.name


def test_pages_have_no_external_script_or_image():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for src in re.findall(r"<(?:script|img)\b[^>]*\bsrc=[\"']([^\"']+)", text):
            assert src.startswith("/static/"), f"{page.name}: {src}"


def test_index_links_stylesheets_in_order_and_has_five_screens():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index("tailwind.css") < html.index("styles.css")
    for name in ("booth", "progress", "result", "gallery", "error"):
        assert f'data-screen="{name}"' in html
    assert 'type="module"' in html


def test_index_has_privacy_footer():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert FOOTER_TEXT in html


def test_messages_js_has_exact_texts():
    js = (STATIC / "js" / "messages.js").read_text(encoding="utf-8")
    for text in (
        "The spirits can only read photos 📸 Please choose a JPG, PNG or WebP image.",
        "🕯️ Developing your photo in the darkroom...",
        "Small photo, the result may be a bit blurry 🌙",
        "Works best with one pet per photo 🐾",
    ):
        assert text in js


def test_main_js_exposes_show_screen():
    js = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    assert "window.showScreen" in js


def test_page_loads_from_root_route(monkeypatch):
    monkeypatch.delenv("USE_FAKE_AGENTS", raising=False)
    client = TestClient(create_app(make_settings()))
    r = client.get("/")
    assert r.status_code == 200
    assert FOOTER_TEXT in r.text
    assert client.get("/static/js/main.js").status_code == 200


# ---- Part 4: booth form (task 8.5) ----
INDEX = STATIC / "index.html"


def test_booth_form_texts_and_chips_are_present():
    html = INDEX.read_text(encoding="utf-8")
    for text in (
        "Works best with one pet per photo 🐾",
        "Using a costume photo? Add details here ✨",
        "Summon Costume",
        "0 / 200",
        "Wizard with purple hat",
        "Vampire cape",
        "Pumpkin costume",
    ):
        assert text in html


def test_file_inputs_have_no_forced_camera():
    # Why: without "capture", phones offer both the camera and the photo library.
    html = INDEX.read_text(encoding="utf-8")
    tags = re.findall(r"<input[^>]*type=\"file\"[^>]*>", html)
    assert len(tags) == 2
    for tag in tags:
        assert "capture" not in tag


def test_description_input_has_maxlength_200_and_example_placeholder():
    html = INDEX.read_text(encoding="utf-8")
    tag = re.search(r'<input id="description"[^>]*>', html, flags=re.S).group(0)
    assert 'maxlength="200"' in tag
    assert 'placeholder="Example:' in tag


def test_summon_button_starts_disabled():
    html = INDEX.read_text(encoding="utf-8")
    tag = re.search(r'<button[^>]*id="summon-button"[^>]*>', html, flags=re.S).group(0)
    assert "disabled" in tag


def test_main_js_wires_prepare_image_and_button_rule():
    js = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    assert "prepareImage" in js
    assert "state.petPrepared" in js and "state.costumePrepared" in js
    assert 'description.trim() !== ""' in js
    assert "MESSAGES.darkroom" in js and "MESSAGES.smallPhoto" in js
