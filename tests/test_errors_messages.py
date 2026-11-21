import re

import pytest

from app.messages import MAX_MESSAGE_LENGTH, MESSAGES, format_relative, get_message

# ---------------------------------------------------------------- messages part


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (1, "1 minute"),
        (59 * 60, "59 minutes"),
        (3599, "1 hour"),
        (60 * 60, "1 hour"),
        (61 * 60, "2 hours"),
        (3 * 3600, "3 hours"),
    ],
)
def test_format_relative_examples(seconds, expected):
    assert format_relative(seconds) == expected


def test_format_relative_minimum_is_one_minute():
    assert format_relative(0) == "1 minute"


EXACT_TEXTS = {
    "visitor_limit": ("🌙 The spirits need rest! Your spells return in 3 hours.", 3 * 3600),
    "global_cap": ("🦇 The photo booth is closed for the night. It reopens in 3 hours!", 3 * 3600),
    "config_error": ("🕸️ The photo booth isn't open yet. The spirits are still setting up!", None),
    "gatekeeper_failed": (
        "👻 The Gatekeeper dozed off and couldn't check your pet. Your try wasn't used, so please try again!",
        None,
    ),
    "credits_depleted": ("🧪 Our cauldron is out of magic. Please come back later!", None),
    "temporary_failure": ("🌩️ A storm is disturbing the spirits. Try again in a moment!", None),
    "refused": ("🔮 The spirits refused this spell. Try a different costume idea!", None),
    "pipeline_timeout": (
        "🧙 The cauldron went cold before the spell finished. Don't worry, it's on the house. Try again!",
        None,
    ),
    "wonky": ("🔮 The spell came out a little wonky this time... Want to summon again?", None),
    "not_verified": (
        "🦉 Our owl inspector fell asleep, so this one wasn't double-checked. Hope you love it!",
        None,
    ),
}


@pytest.mark.parametrize("code", EXACT_TEXTS)
def test_message_exact_text(code):
    expected, seconds = EXACT_TEXTS[code]
    assert get_message(code, seconds) == expected


def test_no_animal_and_bad_costume_start_with_required_text():
    assert get_message("no_animal").startswith("The spirits say that's not a pet! 👻")
    assert get_message("bad_costume") == (
        "The spirits couldn't brew that one 👻 "
        "Try something like 'pirate hat with eye patch' or 'superhero cape'."
    )


def test_all_expected_codes_exist():
    expected = {
        "visitor_limit", "global_cap", "config_error", "no_animal", "bad_costume",
        "gatekeeper_failed", "credits_depleted", "temporary_failure", "refused",
        "maker_failed", "maker_timeout", "pipeline_timeout", "judge_locked",
        "bad_upload", "wonky", "not_verified",
    }  # fmt: skip
    assert set(MESSAGES) == expected


@pytest.mark.parametrize("code", MESSAGES)
def test_message_length_limit(code):
    assert 0 < len(get_message(code, 3 * 3600)) <= MAX_MESSAGE_LENGTH


def test_limit_messages_use_relative_time_and_no_utc():
    for code in ("visitor_limit", "global_cap", "judge_locked"):
        text = get_message(code, 61 * 60)
        assert "2 hours" in text
    for code in MESSAGES:
        text = get_message(code, 3600)
        assert "UTC" not in text
        assert not re.search(r"\d{1,2}:\d{2}", text)


# ----------------------------------------------------------------- errors part

import logging

import httpx
import openai
from hypothesis import given, strategies as st

from app.errors import ERROR_CODES, PawleenError, classify_openai_error

# Built from pieces so the secret scanner does not flag it.
FAKE_KEY = "s" + "k-FAKEKEY1234567890abcdef"
_REQ = httpx.Request("POST", "https://api.openai.com/v1/x")


def _status_exc(cls, status, code=None):
    resp = httpx.Response(status, request=_REQ)
    exc = cls(f"boom {FAKE_KEY}", response=resp, body={"code": code})
    exc.code = code
    return exc


CASES = [
    ("credits_depleted", _status_exc(openai.RateLimitError, 429, "insufficient_quota")),
    ("temporary_failure", _status_exc(openai.RateLimitError, 429, "rate_limit_exceeded")),
    ("temporary_failure", _status_exc(openai.InternalServerError, 500)),
    ("temporary_failure", openai.APIConnectionError(request=_REQ)),
    ("temporary_failure", openai.APITimeoutError(request=_REQ)),
    ("refused", _status_exc(openai.BadRequestError, 400, "moderation_blocked")),
    ("refused", PawleenError("refused")),
    ("temporary_failure", _status_exc(openai.BadRequestError, 400, "other")),
    ("temporary_failure", RuntimeError(FAKE_KEY)),
]


@pytest.mark.parametrize("expected, exc", CASES)
def test_classify_examples(expected, exc):
    assert classify_openai_error(exc) == expected


def test_pawleen_error_code_and_unknown_code():
    assert PawleenError("wonky").code == "wonky"
    with pytest.raises(ValueError):
        PawleenError("nope")
    assert set(ERROR_CODES) == set(MESSAGES)


@pytest.mark.parametrize("expected, exc", CASES)
def test_response_text_never_contains_exception_text(expected, exc):
    text = get_message(classify_openai_error(exc), 3600)
    assert FAKE_KEY not in text
    assert "boom" not in text


@given(st.text())
def test_any_message_maps_to_defined_code_without_leak(msg):
    code = classify_openai_error(RuntimeError(msg + FAKE_KEY))
    assert code in ERROR_CODES
    assert FAKE_KEY not in get_message(code, 3600)


def test_credits_depleted_logs_exactly_one_safe_line(caplog):
    exc = _status_exc(openai.RateLimitError, 429, "insufficient_quota")
    with caplog.at_level(logging.DEBUG):
        classify_openai_error(exc)
    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "credits_depleted" in line
    assert FAKE_KEY not in line and "boom" not in line
    assert caplog.records[0].exc_info is None


SETUP_CASES = [
    (openai.AuthenticationError, 401),
    (openai.PermissionDeniedError, 403),
    (openai.NotFoundError, 404),
]


@pytest.mark.parametrize("cls, status", SETUP_CASES)
def test_setup_errors_map_to_config_error(cls, status):
    assert classify_openai_error(_status_exc(cls, status)) == "config_error"


@pytest.mark.parametrize("cls, status", SETUP_CASES)
def test_setup_errors_log_one_safe_line(cls, status, caplog):
    with caplog.at_level(logging.DEBUG):
        code = classify_openai_error(_status_exc(cls, status))
    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "config_error" in line and cls.__name__ in line
    assert FAKE_KEY not in line and "boom" not in line
    assert caplog.records[0].exc_info is None
    text = get_message(code)
    assert FAKE_KEY not in text and "boom" not in text


def test_unknown_exception_logged_by_type_only(caplog):
    with caplog.at_level(logging.DEBUG):
        classify_openai_error(RuntimeError(FAKE_KEY))
    assert "RuntimeError" in caplog.text
    assert FAKE_KEY not in caplog.text
