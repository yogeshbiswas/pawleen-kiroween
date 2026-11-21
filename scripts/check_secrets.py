"""Block commits that contain secrets.

Usage:
    python scripts/check_secrets.py              # scan staged files
    python scripts/check_secrets.py FILE [...]   # scan the given files (testing)
    python scripts/check_secrets.py --hook       # Kiro PreToolUse hook mode (stdin JSON)

Reports file name and line number only. It never prints a secret value.
Exit code 1 when something is found (2 in --hook mode, which blocks the tool call).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
JUDGE_PASS_PATTERN = re.compile(r"^\s*(?:export\s+)?JUDGE_PASS\s*=\s*(.*?)\s*$")
PLACEHOLDER = "change-me-or-leave-empty"


def _is_env_file(name: str) -> bool:
    return PurePosixPath(name.replace("\\", "/")).name == ".env"


def scan_text(name: str, text: str) -> list[str]:
    """Return findings like 'name:12: reason' for one file's text."""
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if KEY_PATTERN.search(line):
            findings.append(f"{name}:{number}: possible OpenAI API key")
        match = JUDGE_PASS_PATTERN.match(line)
        if match:
            value = match.group(1).strip().strip("\"'")
            if value and value != PLACEHOLDER:
                findings.append(f"{name}:{number}: JUDGE_PASS has a real-looking value")
    return findings


def scan_file(name: str, text: str | None) -> list[str]:
    findings: list[str] = []
    if _is_env_file(name):
        findings.append(f"{name}: .env files must not be committed")
    if text is not None:
        findings.extend(scan_text(name, text))
    return findings


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def scan_staged() -> list[str]:
    names = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").decode("utf-8", "replace").splitlines()
    findings: list[str] = []
    for name in names:
        if not name:
            continue
        try:
            text = _git("show", f":{name}").decode("utf-8", "replace")
        except subprocess.CalledProcessError:
            text = None
        findings.extend(scan_file(name, text))
    return findings


def scan_paths(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        findings.extend(scan_file(path, text))
    return findings


def _report(findings: list[str]) -> str:
    return "Secret check failed. Commit blocked:\n" + "\n".join(f"  {f}" for f in findings)


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if "git commit" not in str(command):
        return 0
    try:
        findings = scan_staged()
    except (OSError, subprocess.CalledProcessError):
        return 0
    if findings:
        print(_report(findings), file=sys.stderr)
        return 2
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--hook"]:
        return run_hook()
    findings = scan_paths(argv) if argv else scan_staged()
    if findings:
        print(_report(findings), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
