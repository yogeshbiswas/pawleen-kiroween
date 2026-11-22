# Build notes

## Tailwind CSS build

Tailwind is built with `pytailwindcss`, a dev-only tool. It is not in
`requirements.txt`, so Render never needs Node.js or the Tailwind binary.
The generated `static/css/tailwind.css` is committed.

| Item | Value |
| --- | --- |
| `pytailwindcss` version | 0.4.2 (pinned in `requirements-dev.txt`) |
| Tailwind CSS version | v4.3.5 |
| `TAILWINDCSS_VERSION` value | `v4.3.5` |

Without `TAILWINDCSS_VERSION`, `pytailwindcss` downloads the latest Tailwind
release, so the output can change over time. Setting it keeps builds repeatable.

## Rebuild command (PowerShell, from the project root)

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
$env:TAILWINDCSS_VERSION = "v4.3.5"
.\.venv\Scripts\tailwindcss -i tailwind/input.css -o static/css/tailwind.css --minify
```

The first run downloads the Tailwind binary (needs internet). Rebuild after
you change `tailwind.config.js`, `tailwind/input.css`, or any class name in
`static/**/*.html` or `static/js/**/*.js`.
