import json

from app.events import ErrorEvent, HeartbeatEvent, ResultEvent, StepEvent, parse_sse


def _split(sse):
    """Check framing and return (event name, data dict)."""
    assert sse.endswith("\n\n")
    lines = sse[:-2].split("\n")
    assert len(lines) == 2
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    return lines[0][7:], json.loads(lines[1][6:])


def test_step_framing_and_fields():
    sse = StepEvent(step="brewing", attempt=2, recast=True).to_sse()
    assert sse == (
        'event: step\ndata: {"step":"brewing","attempt":2,"max_attempts":2,"recast":true}\n\n'
    )


def test_heartbeat():
    assert HeartbeatEvent(t=1700000000).to_sse() == 'event: heartbeat\ndata: {"t":1700000000}\n\n'


def test_result_fields():
    ev = ResultEvent(
        image_b64="AAAA", costume_name="Witch costume", remaining=2, limit=3, notice="wonky",
        message="a bit wonky",
    )  # fmt: skip
    name, data = _split(ev.to_sse())
    assert name == "result"
    assert data == {
        "image_b64": "AAAA", "mime": "image/png", "costume_name": "Witch costume",
        "remaining": 2, "limit": 3, "notice": "wonky", "message": "a bit wonky",
    }  # fmt: skip


def test_result_nulls():
    _, data = _split(ResultEvent(image_b64="A", remaining=0, limit=3).to_sse())
    assert data["costume_name"] is None
    assert data["notice"] is None
    assert data["message"] is None


def test_error_fields():
    ev = ErrorEvent(code="no_animal", message="No pet here", show_chips=True)
    name, data = _split(ev.to_sse())
    assert name == "error"
    assert data == {
        "code": "no_animal", "message": "No pet here", "show_chips": True,
        "retry_after_seconds": None,
    }  # fmt: skip


def test_parse_multi_event_buffer():
    events = [
        StepEvent(step="gatekeeping"),
        HeartbeatEvent(t=5),
        StepEvent(step="checking", attempt=2, recast=True),
        ErrorEvent(code="judge_locked", message="m", retry_after_seconds=60),
    ]
    buffer = "".join(e.to_sse() for e in events)
    assert parse_sse(buffer) == events


def test_parse_skips_unknown_and_broken_blocks():
    text = "event: nope\ndata: {}\n\nevent: step\ndata: {oops\n\n" + HeartbeatEvent(t=1).to_sse()
    assert parse_sse(text) == [HeartbeatEvent(t=1)]
