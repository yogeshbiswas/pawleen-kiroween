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
        "Pick your costume: upload a photo, describe it, or both ✨",
        "Upload a costume photo",
        "Describe the costume",
        "Tip: with a photo, add extra details like colours or accessories",
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


# ---- Part 5: summon stream and progress screen (task 8.6) ----
def test_api_js_has_parse_frame_and_30s_watchdog():
    js = (STATIC / "js" / "api.js").read_text(encoding="utf-8")
    assert "export function parseFrame" in js
    assert "export async function summon" in js
    assert "WATCHDOG_MS = 30000" in js
    assert "X-Judge-Pass" in js


def test_progress_texts_are_present():
    js = (STATIC / "js" / "messages.js").read_text(encoding="utf-8")
    for text in (
        "The Gatekeeper is inspecting your pet...",
        "Brewing the costume spell...",
        "Checking the transformation...",
        "Stirring the cauldron...",
        "Adding a pinch of moonlight...",
        "Almost there, the spell is thickening...",
        "🎃 Your spooky pet is ready!",
    ):
        assert text in js
    assert "Attempt ${data.attempt} of ${data.max_attempts}" in (
        STATIC / "js" / "main.js"
    ).read_text(encoding="utf-8")


def test_progress_screen_has_three_steps_bar_and_error_back_button():
    html = INDEX.read_text(encoding="utf-8")
    for step in ("gatekeeping", "brewing", "checking"):
        assert f'data-step="{step}"' in html
    assert 'id="progress-fill"' in html
    assert 'id="error-back"' in html


# ---- Part 6: Haunted_Gallery (task 10.1) ----
def test_gallery_js_has_store_and_functions():
    js = (STATIC / "js" / "gallery.js").read_text(encoding="utf-8")
    assert 'DB_NAME = "pawleen"' in js and 'STORE = "spells"' in js
    assert 'keyPath: "id"' in js and 'createIndex("savedAt"' in js
    for name in ("saveSpell", "listSpells", "deleteSpell", "clearAll", "costumeNameFor"):
        assert f"export function {name}" in js or f"export async function {name}" in js
    assert '"Mystery costume"' in js
    # Why: gallery contents must never go to the backend (Req 9.14).
    assert "fetch(" not in js


def test_gallery_view_texts_are_present():
    html = INDEX.read_text(encoding="utf-8")
    for text in (
        "🦇 Your gallery lives in this browser. Download your favourites to keep them forever!",
        "🪦 Banish this spell forever? This can't be undone.",
        ">Banish<",
        ">Keep it<",
        "Clear my whole gallery",
    ):
        assert text in html


def test_gallery_code_does_not_send_images_to_backend():
    js = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    start = js.index("Haunted_Gallery view")
    assert "fetch(" not in js[start:] and "summon(" not in js[start:]


# ---- Part 7: Privacy_Banner (task 10.3) ----
def test_privacy_banner_text_and_footer_are_in_index():
    html = INDEX.read_text(encoding="utf-8")
    for text in (
        "processed by OpenAI",
        "not stored on our servers",
        "gallery is stored only in this browser",
        "anonymous cookie counts your daily spells",
        'id="privacy-banner"',
        'id="privacy-banner-dismiss"',
        FOOTER_TEXT,
    ):
        assert text in html


def test_banner_js_uses_the_dismissal_key():
    js = (STATIC / "js" / "banner.js").read_text(encoding="utf-8")
    assert "pawleenBannerDismissed" in js
    assert "fetch(" not in js


# ---- Part 8: logo and favicon (task 14.1) ----
def test_favicon_link_is_inline_svg_in_both_pages():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        assert re.search(
            r'<link rel="icon" href="data:image/svg\+xml,%3Csvg', text
        ), page.name


def test_both_pages_use_the_same_favicon():
    hrefs = [
        re.search(r'<link rel="icon" href="([^"]+)"', p.read_text(encoding="utf-8")).group(1)
        for p in PAGES
    ]
    assert hrefs[0] == hrefs[1]


def test_header_logo_is_decorative_svg_with_visible_name():
    html = INDEX.read_text(encoding="utf-8")
    logo = re.search(r'id="logo">(.*?)</a>', html, flags=re.S).group(1)
    assert '<svg' in logo and 'aria-hidden="true"' in logo
    assert "<span>Pawleen</span>" in logo


def test_no_external_image_is_referenced():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        # Why: previews get their src from JS later, so only a present src is checked.
        for src in re.findall(r"<img\b[^>]*\bsrc=\"([^\"]+)\"", text):
            assert src.startswith(("/static/", "data:")), page.name
        for href in re.findall(r'<link\b[^>]*rel="icon"[^>]*href="([^"]+)"', text):
            assert href.startswith("data:image/svg+xml,"), page.name


# ---- Part 9: fog, bats, ghosts, candle, reduced motion (task 14.2) ----
def test_effects_layers_ignore_pointer_events_and_exist_in_html():
    css = STYLES.read_text(encoding="utf-8")
    base = re.search(r"\.fx-layer\s*\{(.*?)\}", css, flags=re.S).group(1)
    assert "pointer-events: none" in base and "position: fixed" in base
    html = INDEX.read_text(encoding="utf-8")
    for cls in ("fx-fog", "fx-candle", "fx-flyers"):
        assert f"fx-layer {cls}" in html
    assert html.count("fx-bat ") >= 2 and html.count("fx-ghost ") >= 2


def test_reduced_motion_block_stops_effects_and_keeps_progress_bar():
    css = STYLES.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    # Last reduced-motion block holds the effects rules.
    block = css.split("@media (prefers-reduced-motion: reduce)")[-1]
    assert ".fx-fog" in block and ".fx-candle" in block
    assert ".fx-flyers" in block and "display: none" in block
    assert "animation: none" in block
    # Progress bar transition is only disabled in its own block, not here.
    assert "progress-fill" not in block


def test_styles_have_no_external_url_values():
    css = STYLES.read_text(encoding="utf-8")
    assert "http://" not in css and "https://" not in css
    for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
        assert url.startswith("/static/"), url

# ---- Part 10: UI polish (bigger logo, more effects, side panels) ----
def test_effects_counts_and_sizes():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count("fx-bat ") >= 4 and html.count("fx-ghost ") >= 2
    # Why: bats and ghosts must be 40-56 px wide.
    flyers = re.findall(r'class="fx-flyer[^"]*"[^>]*\bwidth="(\d+)"', html)
    assert len(flyers) >= 6
    assert all(40 <= int(w) <= 56 for w in flyers)


def test_logo_is_44px():
    html = INDEX.read_text(encoding="utf-8")
    assert "w-11 h-11" in re.search(r'id="logo">(.*?)</a>', html, flags=re.S).group(1)
    assert ".w-11" in (STATIC / "css" / "tailwind.css").read_text(encoding="utf-8")


def test_side_panels_exist_and_show_only_from_1280px():
    html = INDEX.read_text(encoding="utf-8")
    for text in ("Meet the 3 spirits", "Gatekeeper", "Costume Maker",
                 "Quality Checker", "Haunted Hall of Fame", "examples.js"):
        assert text in html
    css = STYLES.read_text(encoding="utf-8")
    assert re.search(r"\.side-panel\s*\{\s*display:\s*none", css)
    media = css.split("@media (min-width: 1280px)")[1]
    assert "display: block" in media


def test_examples_js_handles_missing_files():
    js = (STATIC / "js" / "examples.js").read_text(encoding="utf-8")
    for n in (1, 2, 3):
        assert f"example-{n}.png" in js
    assert "onerror" in js and "panel.hidden" in js


# ---- Part 11: living bats (bats.js) ----
def test_bats_js_exists_loaded_and_respects_reduced_motion():
    js_path = STATIC / "js" / "bats.js"
    assert js_path.exists()
    assert "/static/js/bats.js" in INDEX.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")
    # Why: the reduced-motion check must come before any animation starts.
    check = js.index("prefers-reduced-motion")
    assert check < js.index("requestAnimationFrame(")
    assert "motionQuery.matches" in js


def test_bats_have_wings_and_orange_eyes():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count("bat-wing-l") == 4 and html.count("bat-wing-r") == 4
    assert html.count('class="bat-eye"') == 8 and html.count("#f97316") >= 8
    css = STYLES.read_text(encoding="utf-8")
    assert "scaleY" in css and "@keyframes bat-flap" in css


def test_bats_js_flies_waypoints_and_pauses_when_hidden():
    js = (STATIC / "js" / "bats.js").read_text(encoding="utf-8")
    assert "requestAnimationFrame" in js and "visibilitychange" in js
    assert "cancelAnimationFrame" in js and "document.hidden" in js
    assert "--bat-flap-time" in js
    assert "bat-flap-time" in STYLES.read_text(encoding="utf-8")


def test_bats_start_and_end_off_screen_and_avoid_bottom_15_percent():
    js = (STATIC / "js" / "bats.js").read_text(encoding="utf-8")
    # Start/end waypoints are beyond the edge by the bat's width plus a margin.
    assert "-size - EDGE_MARGIN" in js and "window.innerWidth + EDGE_MARGIN" in js
    # Bat is placed at its off-screen start before it is shown.
    assert js.index("el.style.transform") < js.index('el.style.visibility = "visible"')
    # Whole bat stays above the bottom 15%.
    assert "h * 0.85 - batHeight" in js


# ---- Part 12: portal, cauldron, glow, accessibility, 404 theme (task 14.3) ----
def _luminance(hex_color: str) -> float:
    """WCAG relative luminance of a #rrggbb color."""
    h = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_img_in_static_html_has_alt():
    for page in STATIC.glob("*.html"):
        for tag in re.findall(r"<img\b[^>]*>", page.read_text(encoding="utf-8")):
            assert re.search(r"\balt=", tag), f"{page.name}: {tag}"


def test_page_background_is_dark():
    css = STYLES.read_text(encoding="utf-8")
    color = re.search(r"html\s*\{[^}]*background:\s*(#[0-9a-fA-F]{6})", css).group(1)
    assert _luminance(color) <= 0.05


def test_focus_visible_rule_exists():
    css = STYLES.read_text(encoding="utf-8")
    assert re.search(r":focus-visible\s*\{[^}]*outline:", css)
    assert ".glow-btn:focus-visible" in css


def test_theme_colors_meet_contrast_minimums():
    night = "#07040d"
    # Body text 4.5:1; large text and UI parts (borders, focus ring) 3:1.
    for text in ("#ede9fe", "#a78bfa", "#f97316", "#fdba74"):
        assert _contrast(text, night) >= 4.5, text
    assert _contrast("#7c3aed", night) >= 3  # borders
    assert _contrast("#f97316", night) >= 3  # focus ring
    assert _contrast(night, "#f97316") >= 4.5  # dark text on orange buttons


def test_portal_cauldron_and_glow_styles_exist():
    css = STYLES.read_text(encoding="utf-8")
    portal = re.search(r"\.portal\s*\{(.*?)\n\}", css, flags=re.S).group(1)
    assert "conic-gradient" in portal and "border-radius: 50%" in portal
    assert ".cauldron::before" in css and "@keyframes bubble-rise" in css
    for state in (".glow-btn {", ".glow-btn:hover", ".glow-btn:focus-visible"):
        assert state in css
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="portal ' in html and 'class="cauldron ' in html


def test_primary_buttons_glow_and_touch_targets_are_44px():
    html = INDEX.read_text(encoding="utf-8")
    for tag in re.findall(r"<button\b[^>]*>", html, flags=re.S):
        if "bg-pumpkin" in tag and "hover:bg-pumpkin" not in tag:
            assert "glow-btn" in tag, tag
    css = STYLES.read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 767px)")[1]
    assert "min-height: 44px" in mobile and "min-width: 44px" in mobile


def test_404_page_uses_the_same_theme():
    html = (STATIC / "404.html").read_text(encoding="utf-8")
    assert "/static/css/styles.css" in html
    assert "#07040d" in html and "glow-btn" in html
    assert 'aria-hidden="true"' in html and "buried" in html


# ---- Part 13: Tailwind rebuild check (task 14.4) ----
LAYOUT_CLASSES = [
    "min-h-screen",
    "flex-col",
    "flex-1",
    "max-w-3xl",
    "mx-auto",
    "gap-6",
    "bg-night",
    "text-pumpkin",
    "border-witch/40",  # slash is escaped in the CSS
    "hover:bg-witch/20",  # colon and slash are escaped
    "min-[400px]:w-auto",  # brackets and colon are escaped
]


def _css_selector(class_name: str) -> str:
    """Build the selector Tailwind writes, e.g. 'sm:flex' -> '.sm\\:flex'."""
    return "." + re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", class_name)


def test_layout_classes_are_used_in_index_and_built_into_tailwind_css():
    # Why: a class in index.html but missing from tailwind.css means a forgotten rebuild.
    html = INDEX.read_text(encoding="utf-8")
    css = (STATIC / "css" / "tailwind.css").read_text(encoding="utf-8")
    for name in LAYOUT_CLASSES:
        assert re.search(rf'class="[^"]*(?<![\w:/\[-]){re.escape(name)}(?![\w/\]-])', html), (
            f"{name} not used in index.html"
        )
        assert _css_selector(name) in css, f"{name} missing: rebuild tailwind.css"

# ---- Part 14: content stays above the effects (phone bug) ----
def test_content_wrappers_are_stacked_above_effects_layers():
    css = STYLES.read_text(encoding="utf-8")
    fx_z = int(re.search(r"\.fx-layer\s*\{[^}]*z-index:\s*(\d+)", css).group(1))
    # Why: z-index only works on positioned elements, so position is checked too.
    rule = re.search(r"header,\s*main,\s*footer\s*\{(.*?)\}", css, flags=re.S).group(1)
    assert "position: relative" in rule
    content_z = int(re.search(r"z-index:\s*(\d+)", rule).group(1))
    assert content_z > fx_z
