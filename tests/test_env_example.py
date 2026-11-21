from pathlib import Path

REQUIRED = [
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_MODEL",
    "OPENAI_VISION_MODEL",
    "OPENAI_IMAGE_QUALITY",
    "JUDGE_PASS",
    "VISITOR_DAILY_LIMIT",
    "JUDGE_DAILY_LIMIT",
    "GLOBAL_DAILY_CAP",
]

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def _parse():
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


def test_all_config_variables_present():
    values = _parse()
    missing = [name for name in REQUIRED if name not in values]
    assert not missing, f"missing from .env.example: {missing}"


def test_no_value_looks_like_a_real_key():
    for name, value in _parse().items():
        assert "sk-" not in value, f"{name} looks like a real key"
