import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_secrets.py"


def _fake_key() -> str:
    return "s" + "k-" + "A1b2C3d4E5f6G7h8I9j0K1l2"


def _run(*paths: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)], capture_output=True, text=True
    )


def test_fake_key_is_flagged_without_printing_it(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\nkey = '" + _fake_key() + "'\n")
    r = _run(f)
    assert r.returncode == 1
    assert ":2:" in r.stderr
    assert _fake_key() not in r.stdout + r.stderr


def test_env_file_name_is_flagged(tmp_path):
    f = tmp_path / ".env"
    f.write_text("FOO=bar\n")
    r = _run(f)
    assert r.returncode == 1
    assert ".env" in r.stderr


def test_env_example_with_placeholders_passes(tmp_path):
    f = tmp_path / ".env.example"
    f.write_text("OPENAI_API_KEY=your-openai-api-key-here\nJUDGE_PASS=change-me-or-leave-empty\n")
    assert _run(f).returncode == 0
    g = tmp_path / "other.example"
    g.write_text("JUDGE_PASS=\n")
    assert _run(g).returncode == 0


def test_real_judge_pass_is_flagged_without_printing_it(tmp_path):
    secret = "hunter" + "2-pumpkin"
    f = tmp_path / "notes.txt"
    f.write_text("JUDGE_PASS=" + secret + "\n")
    r = _run(f)
    assert r.returncode == 1
    assert ":1:" in r.stderr
    assert secret not in r.stdout + r.stderr


def test_hook_ignores_non_commit_commands():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook"],
        input=json.dumps({"tool_input": {"command": "git status"}}),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
