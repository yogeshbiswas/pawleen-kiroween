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
