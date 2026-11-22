"""The live smoke script must never print image data."""

import importlib.util
from pathlib import Path

from app.events import ErrorEvent, ResultEvent, StepEvent

_path = Path(__file__).resolve().parent.parent / "scripts" / "live_smoke.py"
_spec = importlib.util.spec_from_file_location("live_smoke", _path)
live_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live_smoke)


def test_result_event_does_not_print_image_data(capsys):
    # Built from pieces so no long literal blob sits in the test.
    fake_image = "QUJD" * 20
    live_smoke.print_event(
        ResultEvent(image_b64=fake_image, costume_name="Count Fluffula", remaining=2, limit=3)
    )
    out = capsys.readouterr().out
    assert "event: result" in out
    assert "Count Fluffula" in out
    assert fake_image not in out
    assert "QUJD" not in out


def test_other_events_print_their_name(capsys):
    live_smoke.print_event(StepEvent(step="brewing"))
    live_smoke.print_event(ErrorEvent(code="bad_upload", message="secret-ish text"))
    out = capsys.readouterr().out
    assert "event: step" in out
    assert "event: error (code=bad_upload)" in out
    assert "secret-ish text" not in out
