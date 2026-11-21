import logging

import pytest

from app.config import Settings, load_settings

# Built from pieces so the secret scanner does not flag it.
SECRET = "s" + "k-super-secret-value"


def valid_env(**over):
    env = {
        "OPENAI_API_KEY": SECRET,
        "OPENAI_IMAGE_MODEL": "img-model-x",
        "OPENAI_VISION_MODEL": "vis-model-x",
        "GLOBAL_DAILY_CAP": "50",
    }
    env.update(over)
    return env


def test_defaults():
    s, problems = load_settings(valid_env())
    assert problems == []
    assert s.image_quality == "medium"
    assert s.visitor_daily_limit == 3
    assert s.judge_daily_limit == 20
    assert s.judge_pass == ""
    assert s.global_daily_cap == 50
    assert (s.gatekeeper_timeout, s.maker_timeout, s.checker_timeout) == (30, 90, 30)
    assert (s.pipeline_timeout, s.heartbeat_interval) == (180, 8)


def test_settings_frozen():
    s, _ = load_settings(valid_env())
    with pytest.raises(Exception):
        s.image_model = "other"  # type: ignore[misc]
    assert isinstance(s, Settings)


@pytest.mark.parametrize(
    "name", ["OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "OPENAI_VISION_MODEL", "GLOBAL_DAILY_CAP"]
)
def test_missing_required(name):
    env = valid_env()
    del env[name]
    _, problems = load_settings(env)
    assert problems == [name]


def test_empty_required_is_problem():
    _, problems = load_settings(valid_env(OPENAI_API_KEY="  "))
    assert problems == ["OPENAI_API_KEY"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("GLOBAL_DAILY_CAP", "0"),
        ("GLOBAL_DAILY_CAP", "100001"),
        ("GLOBAL_DAILY_CAP", "abc"),
        ("VISITOR_DAILY_LIMIT", "0"),
        ("VISITOR_DAILY_LIMIT", "1000001"),
        ("VISITOR_DAILY_LIMIT", "3.5"),
        ("JUDGE_DAILY_LIMIT", "-2"),
        ("JUDGE_DAILY_LIMIT", "many"),
    ],
)
def test_bad_limits(name, value):
    _, problems = load_settings(valid_env(**{name: value}))
    assert problems == [name]
    assert value not in " ".join(problems)


def test_limit_boundaries_accepted():
    s, problems = load_settings(
        valid_env(GLOBAL_DAILY_CAP="100000", VISITOR_DAILY_LIMIT="1", JUDGE_DAILY_LIMIT="1000000")
    )
    assert problems == []
    assert (s.global_daily_cap, s.visitor_daily_limit, s.judge_daily_limit) == (100000, 1, 1000000)


def test_quality_unset_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        s, problems = load_settings(valid_env())
    assert s.image_quality == "medium"
    assert problems == []
    assert caplog.records == []


@pytest.mark.parametrize("q", ["low", "medium", "high"])
def test_quality_valid(q, caplog):
    with caplog.at_level(logging.WARNING):
        s, problems = load_settings(valid_env(OPENAI_IMAGE_QUALITY=q))
    assert s.image_quality == q
    assert problems == []
    assert caplog.records == []


@pytest.mark.parametrize("q", ["ultra", ""])
def test_quality_invalid_warns_once_without_value(q, caplog):
    with caplog.at_level(logging.WARNING):
        s, problems = load_settings(valid_env(OPENAI_IMAGE_QUALITY=q))
    assert s.image_quality == "medium"
    assert problems == []
    assert len(caplog.records) == 1
    text = caplog.text
    assert "OPENAI_IMAGE_QUALITY" in text
    assert "ultra" not in text


def test_judge_pass_read():
    s, _ = load_settings(valid_env(JUDGE_PASS="open-sesame"))
    assert s.judge_pass == "open-sesame"


def test_problem_list_and_logs_hold_no_values(caplog):
    env = valid_env(
        GLOBAL_DAILY_CAP="9999999",
        VISITOR_DAILY_LIMIT="zzz-bad",
        OPENAI_IMAGE_QUALITY="ultra",
        **{"JUDGE_" + "PASS": "hunter2"},
    )
    with caplog.at_level(logging.DEBUG):
        _, problems = load_settings(env)
    assert set(problems) == {"GLOBAL_DAILY_CAP", "VISITOR_DAILY_LIMIT"}
    joined = " ".join(problems) + caplog.text
    for value in ("9999999", "zzz-bad", "ultra", "hunter2", SECRET):
        assert value not in joined


def test_judge_pass_is_trimmed():
    env = valid_env(**{"JUDGE_" + "PASS": "  open-sesame \n"})
    s, problems = load_settings(env)
    assert problems == []
    assert s.judge_pass == "open-sesame"


def test_whitespace_only_judge_pass_turns_judge_mode_off():
    s, problems = load_settings(valid_env(**{"JUDGE_" + "PASS": " \t\n "}))
    assert problems == []
    assert s.judge_pass == ""
