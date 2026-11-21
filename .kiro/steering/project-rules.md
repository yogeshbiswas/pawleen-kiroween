# Pawleen project rules

## Environment
- Windows + PowerShell. The project virtual environment is `.venv`.
- Always run Python through the venv, for example:
  `.\.venv\Scripts\python -m pip install ...` and `.\.venv\Scripts\python -m pytest -q`
- Never install packages globally.

## Working style
- I am a beginner developer with a QA background. Keep code simple and readable,
  with short comments that explain "why".
- Do one task at a time. After each task, run pytest and show the result.
- Do not run `git commit` or `git push`; I commit myself after reviewing.
- Ask before deleting any file.

## Rules that must never be broken
- Never put secrets (API keys, judge pass) in code, tests, docs or logs.
  Secrets live only in `.env`, which is git-ignored.
- No real OpenAI calls in tests; use the fake agents.
- Every screen must work on mobile (320 px wide and up).
- Keep the spooky tone in user-facing text, but always include the plain action.
- Python first; avoid Node.js.