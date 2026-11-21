# Implementation Plan: Pawleen Photo Booth

## Overview

The plan builds Pawleen in small steps that you can review one at a time. The order is:

1. Project setup, an OpenAI docs check, and a secret-scanning Kiro hook.
2. The backend logic (config, limits, judge pass, scenes, events, pipeline) against FAKE agents. This costs nothing.
3. The API routes and a plain frontend that works end to end with the fake agents (a dev-only `USE_FAKE_AGENTS=1` switch).
4. The real OpenAI agents (Gatekeeper, Costume Maker, Quality Checker).
5. UI polish (logo, fog, bats, candle, reduced motion, mobile checks).
6. README and Render deployment.

Conventions for every task:

- A task that adds Python logic also adds its example tests and ends with "`pytest` passes".
- Python property tests (Hypothesis) are optional sub-tasks marked `*`. Each property has its own file `tests/test_prop_NN_<name>.py`, tagged `# Feature: pawleen-photo-booth, Property N: <title>`, with at least 100 examples.
- Browser (JavaScript and CSS) tasks have no JS test runner (no Node.js step). They end with a short manual check, plus `pytest` passes for the static-asset tests.
- Tasks are checked in order. Checkpoints are where you test by hand.

## Tasks

- [ ] 1. Project setup, OpenAI docs check, and secret-scanning hook
  - [x] 1.1 Scaffold the project
    - Create `requirements.txt` (fastapi, uvicorn, python-multipart, openai, pydantic, python-dotenv, pillow) and `requirements-dev.txt` (`-r requirements.txt`, pytest, pytest-asyncio, hypothesis, httpx, pytailwindcss). Pin exact versions confirmed with `pip index versions`.
    - Create the `app/`, `app/agents/`, `static/`, `tests/` folders with empty `__init__.py` where needed, `pytest.ini` (asyncio mode auto, `-q`), and a minimal `tests/conftest.py`.
    - Confirm `.gitignore` lists `.env`, `__pycache__/`, `.pytest_cache/`, `.hypothesis/`, and virtual environment folders. Add one smoke test `tests/test_smoke.py` that imports `app`.
    - `pytest` passes.
    - _Requirements: 13.7, 13.8, 14.7_

  - [ ] 1.2 Verify OpenAI models, image sizes, and quality options, then update `.env.example`
    - Read the current OpenAI docs for: the image editing model and its `images.edit` parameters, supported portrait `size` values, supported `quality` values, a vision-capable model name, and the Responses API `parse` call shape for the pinned `openai` version.
    - Create `.env.example` with placeholders only: `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_IMAGE_QUALITY`, `JUDGE_PASS`, `VISITOR_DAILY_LIMIT`, `JUDGE_DAILY_LIMIT`, `GLOBAL_DAILY_CAP`, with a comment that model names are examples. Use the verified names.
    - Write `docs/openai-findings.md` with the date checked, links to the pages used, the chosen model names, the portrait `size` to use, the allowed quality values (and any difference from `low`/`medium`/`high`), and the SDK call shapes. State clearly how each finding settles the design's open point on model names, sizes, and quality.
    - Add a tiny test `tests/test_env_example.py` that checks every variable name from the config table is in `.env.example` and that no value looks like a real key (no `sk-` prefix).
    - `pytest` passes.
    - _Requirements: 13.2, 13.3, 13.9, 13.12_

  - [ ] 1.3 Create the Kiro hook that blocks commits containing secrets
    - Write `scripts/check_secrets.py`: scans the staged files (`git diff --cached --name-only`, then the staged content) and exits with code 1 and a message (file name and line number only, never the secret value) when it finds an `sk-` style OpenAI key pattern, a `JUDGE_PASS=` line with a real-looking value (anything other than empty or the placeholder `change-me-or-leave-empty`), or a staged file named `.env` (but `.env.example` is allowed). It also accepts file paths as arguments for testing.
    - Create the Kiro hook with the `createHook` mechanism so it lands in `.kiro/hooks/`: a `PreToolUse` command hook named "Block secrets in commits". It matches the shell tool name, receives the tool call as JSON on stdin, and runs only when the command contains `git commit`. It calls `scripts/check_secrets.py` and exits with code 2 to block the commit, with the script's message on stderr. A PreToolUse hook is the most practical choice because it needs no git setup and it stops the agent before the commit runs.
    - Optional and only if you also commit from a terminal outside Kiro: add a three-line `.git/hooks/pre-commit` example to the README (task 16.2) that runs the same script. Do not add it as a separate hook file here.
    - Write `tests/test_check_secrets.py` with example tests: a fake `sk-` key is flagged, a `.env` file name is flagged, `.env.example` with placeholders passes, a real-looking `JUDGE_PASS=` value is flagged, and the report never prints the secret value.
    - `pytest` passes.
    - _Requirements: 13.7, 13.8, 13.9_

- [ ] 2. Backend foundations: config, messages, errors
  - [ ] 2.1 Implement `app/config.py` with tests
    - Add the frozen `Settings` dataclass and `load_settings(env)` returning `(settings, problems)`. Read `.env` with `python-dotenv` at startup only (not inside `load_settings`).
    - Apply the rules: required `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL`, `OPENAI_VISION_MODEL`, `GLOBAL_DAILY_CAP` (1 to 100,000); optional limits default 3 and 20 (range 1 to 1,000,000); `OPENAI_IMAGE_QUALITY` allowed `low|medium|high`, default `medium`, invalid value logs one warning naming the variable only and is never in the problem list; optional `JUDGE_PASS` (empty means off).
    - Write `tests/test_config.py`: defaults, missing variables, out-of-range and non-numeric limits, quality unset/valid/invalid (`ultra`, empty string), problem list holds names only, log text holds no values.
    - `pytest` passes.
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.10, 13.11, 13.12, 13.14, 11.1, 11.2_

  - [ ]* 2.2 Write property test for configuration validation
    - **Property 16: Configuration validation reports names, never values**
    - File `tests/test_prop_16_config.py`. `pytest` passes.
    - **Validates: Requirements 13.4, 13.5, 13.6, 13.10, 13.11, 13.12, 13.14**

  - [ ] 2.3 Implement `app/messages.py` with tests
    - Add `format_relative(seconds)` (hours rounded up when at least 3600 seconds, otherwise minutes rounded up, minimum 1; "1 hour", "3 hours", "1 minute").
    - Add all backend Spooky_Messages keyed by error code (visitor limit, global cap, config error, no animal, bad costume, gatekeeper failed, credits depleted, temporary failure, refused, maker failed, maker timeout, pipeline timeout, judge locked, bad upload, wonky, not verified). Use the exact texts from the requirements, each at most 160 characters, each with a plain next step.
    - Write `tests/test_errors_messages.py` (messages part): exact text checks, length limit, relative time examples at 1 s, 59 min, 60 min, 61 min, 3 h, and no UTC wording.
    - `pytest` passes.
    - _Requirements: 3.8, 4.10, 4.11, 4.14, 5.10, 5.11, 6.7, 6.10, 10.8, 10.9, 10.10, 11.10, 12.1, 12.2, 12.4, 13.11, 15.9_

  - [ ]* 2.4 Write property test for relative time
    - **Property 5: Relative time rounds up to whole units**
    - File `tests/test_prop_05_relative_time.py`. `pytest` passes.
    - **Validates: Requirements 10.8, 10.9, 10.10**

  - [ ] 2.5 Implement `app/errors.py` with tests
    - Add `PawleenError` with a `code`, the set of defined error codes, and `classify_openai_error(exc)` mapping `RateLimitError` with `insufficient_quota` to `credits_depleted`, 5xx / `APIConnectionError` / `APITimeoutError` to `temporary_failure`, `BadRequestError` with `moderation_blocked` or a refusal to `refused`, and everything else to `temporary_failure`. Use only the exception type, status code, and error code, never the message text.
    - Log exactly one line for `credits_depleted` (time and category only). Unknown exceptions are logged by type only.
    - Extend `tests/test_errors_messages.py` with one example per code, a test that no response text contains exception text or a fake key, and a `caplog` test for the single credits log line.
    - `pytest` passes.
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.7, 12.8_

  - [ ]* 2.6 Write property test for error mapping
    - **Property 17: Error mapping is safe and total**
    - File `tests/test_prop_17_error_mapping.py`. `pytest` passes.
    - **Validates: Requirements 12.1, 12.2, 12.4, 12.7**

- [ ] 3. Usage tracking and judge guard
  - [ ] 3.1 Implement `app/usage.py` (`UsageTracker`) with tests
    - Implement `reserve`, `commit`, `release`, `remaining`, `seconds_until_reset` under one `asyncio.Lock`, with an injectable clock, UTC day rollover, separate judge counts, and global count for non-judges only.
    - Add `FakeClock` to `tests/conftest.py` if it is not there yet.
    - Write `tests/test_usage.py`: 3 successes then the 4th raises `LimitReached` with the reset seconds; global cap blocks visitors but not judges; release leaves counts unchanged; 10 concurrent `asyncio.gather` reserves with limit 3 accept exactly 3; day rollover resets all counts; fresh tracker means zero counts.
    - `pytest` passes.
    - _Requirements: 10.1, 10.2, 10.6, 10.7, 10.11, 10.12, 10.13, 10.14, 10.15, 10.16, 10.17, 11.7, 11.8_

  - [ ]* 3.2 Write property test for limits never exceeded
    - **Property 1: Limits are never exceeded**
    - File `tests/test_prop_01_limits.py` (include a stateful `RuleBasedStateMachine` variant). `pytest` passes.
    - **Validates: Requirements 10.1, 10.2, 10.6, 10.7, 10.16**

  - [ ]* 3.3 Write property test for judge and visitor isolation
    - **Property 3: Judge and visitor counts are isolated**
    - File `tests/test_prop_03_isolation.py`. `pytest` passes.
    - **Validates: Requirements 11.7, 11.8**

  - [ ]* 3.4 Write property test for reset and remaining
    - **Property 4: Reset and remaining are consistent**
    - File `tests/test_prop_04_reset.py`. `pytest` passes.
    - **Validates: Requirements 10.12, 10.13**

  - [ ] 3.5 Implement `app/judge.py` (`JudgeGuard`) with tests
    - Implement `is_valid` (constant-time `hmac.compare_digest`; empty configured pass, empty presented value, or value longer than 128 characters is invalid) and `verify` with the 5-wrong-attempts, 1-hour lockout per Browser_ID using the injectable clock. A locked browser is refused even with the right pass. The pass value is never logged or returned.
    - Write `tests/test_judge.py`: correct pass, wrong pass, empty configured pass rejects everything, 5 wrong attempts lock, 6th attempt (even correct) returns locked with `retry_after_seconds`, lock expires after 1 hour, two browsers locked separately, `caplog` has no pass value.
    - `pytest` passes.
    - _Requirements: 11.2, 11.5, 11.6, 11.10, 11.13, 11.15_

  - [ ]* 3.6 Write property test for judge pass comparison
    - **Property 14: Judge pass comparison**
    - File `tests/test_prop_14_judge_compare.py`. `pytest` passes.
    - **Validates: Requirements 11.2, 11.13**

  - [ ]* 3.7 Write property test for judge lockout
    - **Property 15: Judge lockout**
    - File `tests/test_prop_15_judge_lockout.py`. `pytest` passes.
    - **Validates: Requirements 11.10**

- [ ] 4. Scenes and SSE events
  - [ ] 4.1 Implement `app/scenes.py` with tests
    - Add `KEYWORD_SCENES` (wizard, vampire, pumpkin, pirate, ghost), `GENERIC_SCENES` (at least 6), and `choose_scene(costume_text, previous, rng)`. Keep a small `last_scene` store per Browser_ID.
    - Write `tests/test_scenes.py`: each keyword maps to its scene (any case), generic text never repeats the previous scene, the list has at least 2 entries.
    - `pytest` passes.
    - _Requirements: 5.5, 5.6, 5.7_

  - [ ]* 4.2 Write property test for scene selection
    - **Property 11: Spooky scene selection**
    - File `tests/test_prop_11_scenes.py`. Include the "regeneration reuses the same scene" check at the pipeline level once task 5.2 exists. `pytest` passes.
    - **Validates: Requirements 5.6, 5.7, 5.8**

  - [ ] 4.3 Implement `app/events.py` with tests
    - Add Pydantic event models `step`, `heartbeat`, `result`, `error` with `to_sse()` and `parse_sse()`, matching the design's schema (including `recast`, `attempt`, `max_attempts`, `notice`, `remaining`, `limit`, `show_chips`, `retry_after_seconds`).
    - Write `tests/test_events.py`: exact SSE framing (`event:` / `data:` / blank line), one example per event type, and a parse of a multi-event buffer.
    - `pytest` passes.
    - _Requirements: 7.1, 7.2, 7.8, 8.11, 12.7_

  - [ ]* 4.4 Write property test for SSE round trip
    - **Property 18: SSE event round trip**
    - File `tests/test_prop_18_sse_roundtrip.py`. `pytest` passes.
    - **Validates: Requirements 7.1, 7.2, 12.7**

- [ ] 5. Fake agents and the pipeline orchestrator
  - [ ] 5.1 Add data models, agent interfaces, and fake agents
    - Create `app/models.py` with `CostumeRequest` (with `costume_text` and a `__repr__` that prints sizes only), `PipelineState`, `PipelineOutcome` (`Success`, `Failure`), and `GatekeeperDecision` / `CheckResult` types. Create the agent classes' interfaces (`app/agents/*.py` stubs with the method signatures from the design that raise `NotImplementedError`; they are filled in by tasks 12.x).
    - In `tests/conftest.py` add scripted `FakeGatekeeper`, `FakeCostumeMaker`, `FakeQualityChecker` (outcomes: a value, an exception, or `"hang"`; they record `calls`), `test_settings()` with tiny timeouts, and tiny fake PNG/JPEG byte helpers. Add an autouse fixture that fails the test if `openai.AsyncOpenAI` is created.
    - For the dev-run fakes, also create `app/fakes.py` with ready-to-use fake agents (gatekeeper accepts, maker returns a generated placeholder PNG made with Pillow after a short delay, checker passes) used by `USE_FAKE_AGENTS=1` in task 6.1.
    - Write `tests/test_models.py`: `costume_text` falls back from description to Costume_Name; `repr` contains no bytes.
    - `pytest` passes.
    - _Requirements: 3.4, 4.15, 4.16, 16.8_

  - [ ] 5.2 Implement `app/pipeline.py` with tests
    - Implement `run_pipeline(req, agents, settings, emit, scene)` and `with_silent_retry`. Follow the design flow exactly: gatekeeper (30 s, one silent retry), maker (90 s, no retry on timeout), checker (30 s, one silent retry), at most one regeneration with the failure reasons and the same scene, best-of-two selection, `not_verified` and `wonky` notices, and `state.best_image` updated as soon as an image exists. Credits and safety errors are not retried.
    - Write `tests/test_pipeline.py` with the scripted fakes: all-pass; one failed check triggers exactly one regeneration with reasons in the prompt; second failure returns the better image with `wonky`; checker fails twice on image 1 gives `not_verified` and no regeneration; checker timeout then success is silent; checker fails twice on image 2 gives `not_verified`; gatekeeper reject skips maker and checker; gatekeeper hang is retried once then `gatekeeper_failed`; maker hang gives `maker_timeout` after exactly one maker call; a `step` event precedes each agent call; regeneration events carry `attempt=2, recast=true`.
    - `pytest` passes.
    - _Requirements: 4.1, 4.9, 4.13, 4.14, 5.1, 5.8, 5.9, 5.10, 5.11, 6.1, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 7.1, 7.8_

  - [ ]* 5.3 Write property test for bounded silent retries
    - **Property 7: Silent retries are bounded and the maker is never retried on timeout**
    - File `tests/test_prop_07_retries.py`. `pytest` passes.
    - **Validates: Requirements 4.13, 4.14, 5.10, 6.6, 6.7**

  - [ ]* 5.4 Write property test for at most one regeneration
    - **Property 8: At most one regeneration**
    - File `tests/test_prop_08_regeneration.py`. `pytest` passes.
    - **Validates: Requirements 6.8, 6.12**

  - [ ]* 5.5 Write property test for best-of-two selection
    - **Property 9: Best-of-two selection**
    - File `tests/test_prop_09_best_of_two.py`. `pytest` passes.
    - **Validates: Requirements 6.10, 6.11**

  - [ ]* 5.6 Write property test for rejection skipping downstream agents
    - **Property 10: Rejection skips downstream agents**
    - File `tests/test_prop_10_rejection.py`. `pytest` passes.
    - **Validates: Requirements 4.9, 4.12**

- [ ] 6. API routes and hosting
  - [ ] 6.1 Implement `app/main.py` (app factory, health, static, 404, PORT) with tests
    - Add `create_app(settings, agents=None)`: loads settings, sets `pipeline_enabled`, mounts `/static`, serves `/` from `static/index.html`, `/health` (`{"status":"ok"}`), and the 404 handler (HTML `static/404.html` with status 404 for non-`/api` paths, JSON 404 for `/api/...`; never `index.html`).
    - Add `python -m app.main`: reads `PORT` (default 8000; exit code 1 with an stderr message naming the value when not an integer from 1 to 65535) and runs uvicorn on `0.0.0.0` with one process.
    - Add the dev switch: `USE_FAKE_AGENTS=1` uses `app/fakes.py` agents and logs one warning that the fake mode is on. Add it, commented out, to `.env.example`. It must be off by default.
    - Create a placeholder `static/index.html` ("Pawleen is waking up") and the real `static/404.html` with "🪦 This page has been buried..." and a button linking to `/`.
    - Write `tests/test_hosting.py`: `/health` 200 quickly, `/` serves the page, unknown path returns 404 with the "buried" text and not the index page, `/api/nope` returns JSON 404, invalid `PORT` values (`abc`, `0`, `70000`) exit non-zero with the value named, config problems leave `/health` and static files working.
    - `pytest` passes.
    - _Requirements: 13.6, 13.10, 13.11, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8_

  - [ ] 6.2 Implement upload validation with tests
    - Add `app/uploads.py`: `validate_upload(content_type, size)` (JPEG, PNG, WebP only; size greater than 0 and at most 10,485,760 bytes), description trimming to 200 characters, and a helper that reads an `UploadFile` and always closes it in a `finally` block.
    - Write `tests/test_uploads.py`: valid types, wrong type, 0 bytes, exactly 10 MiB accepted, 10 MiB + 1 rejected, description trimmed to 200, the file is closed after read even when reading raises.
    - `pytest` passes.
    - _Requirements: 3.2, 3.3, 3.5, 16.3_

  - [ ]* 6.3 Write property test for upload validation
    - **Property 6: Upload validation accepts exactly the allowed files**
    - File `tests/test_prop_06_uploads.py`. `pytest` passes.
    - **Validates: Requirements 3.2, 3.3, 3.5**

  - [ ] 6.4 Implement the usage and judge routes with tests
    - In `app/routes.py` add the `get_browser_id` dependency (cookie `browser_id`: HttpOnly, SameSite=Lax, Secure on HTTPS, 1 year, `secrets.token_urlsafe(16)`; fallback `anon:` + hash of first `X-Forwarded-For` entry and user agent), `GET /api/usage` (`remaining`, `limit`, `is_judge`, `reset_in_seconds`, using the `X-Judge-Pass` header with `is_valid` only), and `POST /api/judge` (`valid`, `remaining`, or 429 `judge_locked` with `retry_after_seconds`). Register the router in `create_app`.
    - Write `tests/test_routes_usage_judge.py`: cookie issued when missing, fallback id without cookie, usage numbers for visitor and judge, valid and invalid pass, 5 wrong then locked, the pass value never appears in any response or log, two browsers have separate judge counts.
    - `pytest` passes.
    - _Requirements: 10.3, 10.4, 10.5, 10.13, 11.3, 11.6, 11.7, 11.10, 11.15_

  - [ ] 6.5 Implement `POST /api/summon` (SSE stream and accounting) with tests
    - In `app/routes.py` add the summon route: check config, validate files (close both uploads in `finally`), `reserve()`, then stream SSE with the required headers (`text/event-stream`, `no-cache, no-transform`, `X-Accel-Buffering: no`, `keep-alive`). Run the pipeline as a task wrapped in `asyncio.timeout(settings.pipeline_timeout)`, feed events through an `asyncio.Queue`, send a `heartbeat` on each queue wait timeout, end with exactly one `result` or `error`. Commit on `result`; release in `finally` on every other path (error, timeout, disconnect, cancel). On timeout with an image, return it with `not_verified` and commit. Pick the scene with `choose_scene`. Put `remaining` and `limit` in the `result` event after the commit.
    - Return the pre-stream JSON errors (`bad_upload` 400, `visitor_limit` / `global_cap` 429 with `retry_after_seconds`, `config_error` 503) in the order: config, files, reserve.
    - Write `tests/test_routes_summon.py` with fake agents: success stream shape and counts, 4th request returns 429, global cap, judge pass raises the limit, every error code leaves counts unchanged, total timeout without image returns `pipeline_timeout` and count 0, total timeout after image 1 returns it as `not_verified` and count 1, heartbeat appears while a fake agent sleeps past the interval, exactly one terminal event, no-buffering headers, cancelling the stream releases the reservation, config error keeps `/health` working.
    - `pytest` passes.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 3.8, 3.9, 4.12, 4.14, 6.13, 7.1, 7.2, 10.6, 10.7, 10.11, 10.17, 11.7, 12.5, 13.11_

  - [ ]* 6.6 Write property test for "only returned images are counted"
    - **Property 2: Only returned images are counted**
    - File `tests/test_prop_02_counting.py` (random scripts for the three fakes run through the route accounting). `pytest` passes.
    - **Validates: Requirements 3.8, 3.9, 4.12, 4.14, 6.13, 10.17, 12.5**

  - [ ] 6.7 Add privacy tests for the backend
    - Write `tests/test_privacy.py`: a spy upload object reports `closed` for both photos after success, validation failure, and pipeline error; the temp directory listing is unchanged after a run, including an upload above 1 MB that makes Starlette spool to disk; `caplog` at DEBUG contains no base64 or raw bytes; the credits-depleted path logs exactly one entry with no key; no code path writes images to disk (grep-style test over `app/` for `open(` write modes and `.write_bytes`).
    - Fix any issue the tests reveal in `routes.py`.
    - `pytest` passes.
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.8, 12.8_

- [ ] 7. Checkpoint - Backend works with fake agents
  - Run `pytest` and make sure it passes.
  - By hand: set `USE_FAKE_AGENTS=1`, `GLOBAL_DAILY_CAP=50`, and fake values for the other required variables, then run `python -m app.main`. Open `http://localhost:8000/health` and an unknown path to see the 404 page. From a terminal, send a `curl -N -F pet_photo=@some.jpg -F description="wizard hat" http://localhost:8000/api/summon` and check that `step`, `heartbeat` (if slow), and `result` events appear.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Frontend skeleton working end to end with fake agents
  - [ ] 8.1 Set up the Tailwind build with pytailwindcss
    - Create `tailwind.config.js` (content paths, `night`, `witch`, `pumpkin` colors, `display` and `body` font families), `tailwind/input.css` (`@import "tailwindcss"; @config; @source` lines) as in the design, and run `tailwindcss -i tailwind/input.css -o static/css/tailwind.css --minify`. Commit the generated file. Note the exact `pytailwindcss` / Tailwind version used in `docs/openai-findings.md`'s sibling file `docs/build-notes.md` (and the `TAILWINDCSS_VERSION` value).
    - Add `tests/test_static_assets.py` (first part): `static/css/tailwind.css` exists and is not empty; `tailwind.config.js` and `tailwind/input.css` exist; `requirements.txt` does not list `pytailwindcss` while `requirements-dev.txt` does.
    - `pytest` passes.
    - _Requirements: 14.9, 14.7_

  - [ ] 8.2 Add self-hosted fonts and license files
    - Download `Creepster-Regular.woff2` and `Inter-Variable.woff2` (latin subset) from the official sources into `static/fonts/`, plus `Creepster-OFL.txt` and `Inter-OFL.txt` from the same sources. Confirm each license text matches the downloaded version.
    - Create `static/css/styles.css` with the two `@font-face` rules (`font-display: swap`, same-origin `/static/fonts/...` URLs) and the font stacks with generic fallbacks (`"Creepster", serif`, `"Inter", sans-serif`), with headings at `font-weight: 400`.
    - Extend `tests/test_static_assets.py`: both `woff2` files and both license files exist; `styles.css` declares both fonts with `font-display: swap`; every `url(...)` in `styles.css` is a same-origin path; no CDN or Google Fonts reference anywhere in `static/`.
    - `pytest` passes.
    - _Requirements: 15.5, 15.19, 16.9_

  - [ ] 8.3 Build the page skeleton: screens, top bar, footer, and base styles
    - Replace the placeholder `static/index.html` with the real page: `<link>` tags for `tailwind.css` then `styles.css`, a top bar (logo placeholder text, Booth/Gallery nav button, Sound toggle placeholder), five `<section>` screens (`booth`, `progress`, `result`, `gallery`, `error`), and the privacy footer line "🔒 Your photos are only used to create your costume (processed by OpenAI) and are never stored on our servers. Your gallery stays in your browser." on every screen. Use a dark `#07040d` background, purple and orange accents, and mobile-first layout.
    - Create `static/js/main.js` (module) with the `state` object and `showScreen(name)`, and `static/js/messages.js` with the frontend-only spooky text (file type, unreadable file, description trimmed, darkroom, small photo, one-pet tip).
    - Rebuild `tailwind.css` with the build command.
    - Extend `tests/test_static_assets.py`: `index.html` and `404.html` contain no `http://` or `https://` URL to another origin, no Tailwind CDN, no external script or image; the footer text is present; the page loads from `/` in a route test.
    - Manual check: the page opens, the screens switch from the browser console with `showScreen('result')`. `pytest` passes.
    - _Requirements: 14.9, 15.1, 15.2, 15.9, 15.10, 15.18, 16.7, 16.9_

  - [ ] 8.4 Implement image preparation (`static/js/image-prep.js`)
    - Export `prepareImage(file)` returning `{ blob, width, height, small }` and throwing `PrepError('type'|'unreadable')`: check type (JPEG, PNG, WebP) and size greater than 0, decode with `createImageBitmap(file, { imageOrientation: 'from-image' })`, always re-encode through a canvas to at most 2048 px on the longest side as JPEG at quality 0.9 (then 0.8, 0.7 if still 10 MB or more, then fail as `unreadable`), and set `small` when the shorter side is below 512.
    - Keep pure helpers (size calculation) as small exported functions with comments describing the expected values, so they can be checked in the console.
    - Manual check list (put it as a comment block at the top of the file): rotated phone photo shows upright, a 12 MP photo ends under 10 MB and 2048 px, a `.txt` file renamed to `.jpg` fails as `unreadable`, a 0-byte file fails.
    - `pytest` passes.
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.9, 2.9, 2.10_

  - [ ] 8.5 Build the booth form (pet portal, costume cauldron, chips, button rules)
    - In `index.html` and `main.js` add: the Pet_Photo upload (file input without a forced camera so mobile offers camera or library, preview, remove button, darkroom message, small-photo note, the "Works best with one pet per photo 🐾" tip), the Costume_Photo upload (preview, remove), the Costume_Description input with an example placeholder, the hint "Using a costume photo? Add details here ✨", at least three Example_Chips ("Wizard with purple hat", "Vampire cape", "Pumpkin costume"), a live "N / 200" counter, `maxlength` 200 with a trim message on paste, and the "Summon Costume" button.
    - Wire `prepareImage`: a rejected file keeps the previous selection and preview and shows the spooky message; a new valid pet photo replaces the old one and dismisses the message; remove clears the preview; the pet photo stays selected after a generation.
    - Enable the button only when `petPrepared && (costumePrepared || description.trim() !== '')`, and disable it while a request runs.
    - Rebuild `tailwind.css`. Manual check against the rules above on a desktop browser. `pytest` passes.
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 3.6_

  - [ ] 8.6 Implement the summon stream and the Progress_Screen
    - Create `static/js/api.js` with `summon(formData, judgePass, onEvent, signal)` (fetch plus `ReadableStream`, SSE frame parser exported as `parseFrame`) and a 30-second watchdog that is reset by every event including `heartbeat`.
    - In `main.js` and `index.html` build the Progress_Screen: three step rows (pending dimmed, active glowing, complete ✅), a glowing progress bar (0, 33, 66, 100 %), the step messages ("The Gatekeeper is inspecting your pet...", "Brewing the costume spell...", "Checking the transformation..."), the 4-second line rotation during brewing, the recast message with "Attempt 2 of 2", and the final "🎃 Your spooky pet is ready!".
    - Handle failures: pre-stream JSON errors and `error` events replace the screen within 1 second with the spooky message (plus Example_Chips when `show_chips`) and a back button; the watchdog shows a "connection lost" message with a back button; back returns to the booth with all selections kept. Send the form data within 500 ms of the click.
    - Rebuild `tailwind.css`. Manual check with `USE_FAKE_AGENTS=1`: a full run shows all three steps then moves to the result screen. `pytest` passes.
    - _Requirements: 3.1, 3.3, 3.6, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 4.10, 4.11, 12.4, 12.6, 13.11_

  - [ ] 8.7 Build the Result_View with Before/After, download, share, and next actions
    - Show the costumed image in a portrait container with `object-fit: contain` (every pixel visible), the Before_After_View with the original pet preview next to it, a download button (object URL, full resolution, PNG; show an error message and keep the button on failure), a share button shown only when `navigator.canShare({ files })` is true (fall back to download when sharing is unavailable or fails), "Try another costume" (clears costume fields, keeps the pet), "New pet" (clears everything), and the "🕯️ N spells left tonight" line (singular for 1, "0 spells left tonight" for 0).
    - Add the fog-clearing reveal as a CSS animation in `styles.css`.
    - Rebuild `tailwind.css`. Manual check with the fake agents. `pytest` passes.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 15.13_

- [ ] 9. Checkpoint - Browser test of the full fake flow, desktop and mobile width
  - Run `pytest` and make sure it passes.
  - Start the app with `USE_FAKE_AGENTS=1` and test in the browser: upload a pet photo, type a costume, summon, watch the progress, see the result, download it, try another costume, start a new pet. Try a wrong file type and a pasted text longer than 200 characters.
  - Mobile-width check: open browser devtools device mode and test at 320, 360, and 390 px wide. Check that there is no horizontal scrollbar, buttons are easy to tap (at least 44 px), and every screen is readable.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Gallery, judge pass, privacy banner, and sound
  - [ ] 10.1 Implement the Haunted_Gallery (`static/js/gallery.js`) and its view
    - Create `gallery.js` with IndexedDB database `pawleen`, store `spells` (`id`, `blob`, `costumeName`, `savedAt`, index on `savedAt`), and `saveSpell`, `listSpells` (newest first), `deleteSpell`, `clearAll`, plus the exported `costumeNameFor(description, gatekeeperName)` rule (description, else Costume_Name, else "Mystery costume").
    - In `main.js` and `index.html`: save the result image within 2 seconds of receiving it (decode base64 to a Blob); the gallery view with thumbnails (newest first, name and date), the hint "🦇 Your gallery lives in this browser. Download your favourites to keep them forever!", a detail view (original size scaled to fit, download, share, delete), the shared "🪦 Banish this spell forever? This can't be undone." dialog with "Banish" and "Keep it" (focus trapped and returned), "Clear my whole gallery", and the empty-state message. Handle a full or unavailable store (message plus download still available) and a failed read (message, nothing deleted). Send nothing from the gallery to the backend.
    - Rebuild `tailwind.css`. Manual check: save, reload (same order), delete, keep, clear all. `pytest` passes.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 9.15, 9.16, 4.16_

  - [ ] 10.2 Add the Judge_Pass box, usage display, and limit messages
    - In `api.js` add `getUsage()` and `checkJudge(pass)` (10-second timeout). In `main.js` and `index.html`: the "Have a judge pass?" box (1 to 128 characters), the `?pass=` flow (submit within 1 second of load, remove the parameter with `history.replaceState` on success), store the valid pass in `sessionStorage` (`pawleenJudgePass`) and send it as `X-Judge-Pass`, the messages for welcome ("🔑 Welcome, honoured judge! The crypt is open, with N spells for tonight."), invalid pass (previous stored pass unchanged), crypt sealed with a relative time, and "could not be checked". Show the visitor and global limit messages with relative reset times from `retry_after_seconds` (hours rounded up at 1 hour or more, otherwise minutes; never UTC).
    - Add a small exported `formatRelative(seconds)` in `messages.js` that matches the backend rule.
    - Rebuild `tailwind.css`. Manual check with `JUDGE_PASS` set in `.env`, including a wrong pass 5 times. `pytest` passes.
    - _Requirements: 10.8, 10.9, 10.10, 11.3, 11.4, 11.5, 11.9, 11.10, 11.11, 11.12, 11.14_

  - [ ] 10.3 Add the Privacy_Banner
    - Show a dismissible banner on the first visit that says photos are processed by OpenAI, photos are not stored on the servers, the gallery is stored only in the browser, and an anonymous Browser_ID cookie counts daily spells. Dismissal is saved in `localStorage.pawleenBannerDismissed` and the banner stays hidden on later visits.
    - Extend `tests/test_static_assets.py` to check the banner text and the footer text are in `index.html`.
    - Rebuild `tailwind.css`. Manual check: banner shows, dismiss, reload. `pytest` passes.
    - _Requirements: 16.5, 16.6, 16.7_

  - [ ] 10.4 Add the Sound_Toggle and sound effects (`static/js/sound.js`)
    - Create `sound.js` with `enabled` off by default (saved in `localStorage.pawleenSound`) and short WebAudio tones for submit, step complete, and result. Add the top-bar toggle with `aria-pressed`, reachable on every screen. No audio files.
    - Rebuild `tailwind.css`. Manual check: silent by default, toggle on and hear tones, reload keeps the setting. `pytest` passes.
    - _Requirements: 15.17, 15.9_

- [ ] 11. Checkpoint - Full fake-agent app in the browser
  - Run `pytest` and make sure it passes.
  - Test in the browser with fake agents: gallery save and reload, delete, clear all; judge pass through the box and through `?pass=`; limit message after 3 summons; privacy banner; sound toggle. Repeat the key flows at 320 to 390 px width in devtools.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Connect the real OpenAI agents
  - [ ] 12.1 Implement `app/openai_client.py` with tests (mocked SDK)
    - Create one shared `AsyncOpenAI(api_key=..., max_retries=0)` factory and the two thin wrappers `vision_json(...)` (Responses API `parse` with a Pydantic `text_format`, an `input_image` data URL, per-call timeout; a `None` parsed result becomes `refused` when there is a refusal item, otherwise a retriable bad output) and `edit_image(...)` (`images.edit` with `model`, one or two images, `prompt`, the portrait `size` and the allowed quality values confirmed in task 1.2, `quality=settings.image_quality`, per-call timeout, base64 decoded to PNG bytes). Use the call shapes recorded in `docs/openai-findings.md`.
    - Write `tests/test_openai_client.py` with a mocked SDK: client built with `max_retries=0`, `edit_image` receives the env model, portrait size, and `quality` equal to each of `low`, `medium`, `high`, and both images when a costume photo exists; `vision_json` passes `text_format` and the env model; a missing image in the response raises a mapped error; no image data appears in logs.
    - `pytest` passes.
    - _Requirements: 4.2, 5.1, 5.9, 6.1, 13.2, 13.3, 13.13, 16.4, 16.8_

  - [ ] 12.2 Implement the real Gatekeeper (`app/agents/gatekeeper.py`) with tests
    - Build the `GatekeeperVerdict` schema and the system prompt for Requirement 4 (any animal accepted, several animals fine, humans with an animal fine, reject only for no animal, unintelligible or harmful description, harmful or unrelated costume photo). Return a `GatekeeperDecision` and add `normalize_costume_name(name, description)` (strip, cut to 40 characters, `None` when a description exists or the text is empty or whitespace).
    - Write `tests/test_gatekeeper.py` with a mocked `vision_json`: accept, reject for no animal, reject for a bad description, reject for a harmful costume photo, photo-only request returns a name of at most 40 characters, description request returns no name, the reason maps to `no_animal` or `bad_costume`, the env vision model is used.
    - `pytest` passes.
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.15, 4.16_

  - [ ] 12.3 Implement the real Costume Maker (`app/agents/costume_maker.py`) with tests
    - Add `build_prompt(costume_text, scene, failure_reasons)` containing the preserve-appearance, portrait-orientation, full pet and full costume centered with at least 5 % margin, scene, and dress-only-the-animals instructions, plus "Fix these problems: ..." when reasons are given, and a costume-reference line when a costume photo exists. Implement `make(req, scene, failure_reasons)` through `edit_image` with `quality` from settings on every call.
    - Write `tests/test_costume_maker.py`: every required instruction is in the prompt, reasons are included on regeneration, the quality value reaches the fake unchanged for `low`, `medium`, `high` including on the regeneration call, a costume photo is passed as a second image, a failed call or no image raises.
    - `pytest` passes.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.8, 5.11, 6.8, 13.13_

  - [ ] 12.4 Implement the real Quality Checker (`app/agents/quality_checker.py`) with tests
    - Build the `CheckResult` schema (`same_pet`, `costume_applied`, `no_cropping`, `reasons`, `passed_count`, `all_passed`) and the prompt using the rules for same species and primary coat colors, visible costume, and cropping fails only when head, ears, hat, paws, or main costume is cut off (a tail tip or cape edge touching the border passes). Send the original pet and the costumed image.
    - Write `tests/test_quality_checker.py` with a mocked `vision_json`: all pass, each single check failing with its reason, `passed_count` values, the prompt contains the three rules, the env vision model is used.
    - `pytest` passes.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 12.5 Write property test for costume name rules
    - **Property 13: Costume name rules**
    - File `tests/test_prop_13_costume_name.py`. `pytest` passes.
    - **Validates: Requirements 4.15, 4.16**

  - [ ]* 12.6 Write property test for prompt contents
    - **Property 12: Prompts contain the required instructions**
    - File `tests/test_prop_12_prompts.py`. `pytest` passes.
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 6.8**

  - [ ] 12.7 Wire the real agents into the app
    - In `create_app` and `app/main.py` build the real agents from `openai_client` when `USE_FAKE_AGENTS` is not set and the config has no problems. Keep passing fake agents through the `agents` argument for tests.
    - Write `tests/test_wiring.py`: with a valid config and no fake flag the real agent classes are used (the OpenAI client is a mocked factory); with `USE_FAKE_AGENTS=1` the fakes are used; with a config problem the pipeline stays disabled and summon returns `config_error`.
    - `pytest` passes.
    - _Requirements: 13.1, 13.10, 13.11, 14.1_

  - [ ] 12.8 Add a manual live smoke script
    - Create `scripts/live_smoke.py` that sends one real summon request to a base URL (default `http://localhost:8000`) with a sample pet image path from the command line, prints each SSE event name and the final status (never the image data or any key), and saves the result PNG to a local path you choose. It is run by hand only and is not part of `pytest`.
    - Add a small test that imports the script's event-printing helper and checks that it never prints image data.
    - `pytest` passes.
    - _Requirements: 5.1, 6.1, 16.8_

- [ ] 13. Checkpoint - Live test with the real OpenAI API
  - Run `pytest` and make sure it passes.
  - Fill in your real `.env` (it is git-ignored). Run `python -m app.main` without `USE_FAKE_AGENTS`, and do one real summon in the browser with a pet photo and a wizard costume. Check the scene, the pet likeness, the progress steps, and that the quality value is accepted by the image model. If `quality` or `size` is rejected, update `docs/openai-findings.md`, `.env.example`, and the code, then repeat.
  - Try a non-pet photo (expect "not a pet") and an odd costume text (expect the costume message with chips). Check that the daily count only goes down after a returned image.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. UI polish
  - [ ] 14.1 Create the logo and favicon
    - Design a ghost with a paw print as an inline SVG in the header (decorative, `aria-hidden="true"`, with the product name as visible text next to it) and use the same SVG, URL-encoded, as the favicon (`<link rel="icon" href="data:image/svg+xml,...">`). Use the same favicon in `404.html`.
    - Extend `tests/test_static_assets.py`: the favicon link exists in `index.html` and `404.html`, and no external image is referenced.
    - Rebuild `tailwind.css`. Manual check in the browser tab. `pytest` passes.
    - _Requirements: 15.16, 15.11, 15.18_

  - [ ] 14.2 Add the fog, floating bats and ghosts, candle glow, and reduced-motion rules
    - In `styles.css` add: a fixed, `pointer-events: none` animated fog (two radial-gradient layers that drift), a few tiny inline-SVG bats and ghosts floating with CSS animation, and a pulsing candle glow. Create everything with CSS or inline SVG only.
    - Add `@media (prefers-reduced-motion: reduce)` that turns off the fog drift, bats and ghosts, candle flicker, the reveal, and other non-essential animations (fog becomes a static background and the result shows at once), while the progress bar width change stays.
    - Extend `tests/test_static_assets.py`: `styles.css` contains the `prefers-reduced-motion` block, `pointer-events: none` on the effects layers, and no external `url(` values.
    - Manual check: effects visible, clicks pass through, then turn on "reduce motion" in the OS or devtools rendering panel and confirm they stop. `pytest` passes.
    - _Requirements: 15.3, 15.8, 15.15, 15.18_

  - [ ] 14.3 Style the portal, cauldron, glowing buttons, accessibility, and 404 page
    - Style the pet upload as a glowing portal (oval with a conic-gradient swirl border) and the costume area as a bubbling cauldron (pot shape with CSS bubbles). Give every primary button a colored glow in default, hover, and `:focus-visible` states. Under 768 px give every control at least 44 x 44 px.
    - Check contrast (4.5:1 body text, 3:1 large text, borders, and focus rings), add `alt` text to every meaningful image and `aria-hidden` to decorative ones, keep a logical tab order and visible focus indicators, and check that dialogs trap and return focus. Apply the same theme to `404.html`.
    - Extend `tests/test_static_assets.py`: every `<img>` in `static/*.html` has an `alt` attribute, the page background color's luminance is at most 0.05 (computed in the test), and the `:focus-visible` rule exists.
    - Rebuild `tailwind.css`. Manual check by keyboard only. `pytest` passes.
    - _Requirements: 15.1, 15.2, 15.4, 15.6, 15.7, 15.11, 15.12, 15.14, 14.3_

  - [ ] 14.4 Rebuild the CSS and run the static checks
    - Run the Tailwind build command one last time, commit `static/css/tailwind.css`, and make sure the README build note (task 16.2) matches the command used.
    - Add a test in `tests/test_static_assets.py` that every Tailwind-style class used for the main layout in `index.html` (a short fixed list you choose) appears in `tailwind.css`, to catch a forgotten rebuild.
    - `pytest` passes.
    - _Requirements: 14.9, 14.10_

- [ ] 15. Checkpoint - Polish and mobile-width check
  - Run `pytest` and make sure it passes.
  - In the browser at 320, 360, and 390 px (devtools device mode) and again at 768, 1280, and 1920 px: no horizontal scrollbar, tap targets are comfortable, the fog, bats, and candle do not block clicks, headings use the spooky font, the logo and favicon show, the result image is fully visible. Test once more with reduced motion enabled and once with the keyboard only.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Final integration, README, and Render deployment
  - [ ] 16.1 Add the end-to-end integration test
    - Write `tests/test_integration.py` using `create_app` with fake agents and `httpx`: a full run from cookie issue, usage check, summon stream, result event with `remaining`, to usage after the run; a rejected run leaves usage unchanged; a judge run uses the judge count; a restart (new app instance) resets counts.
    - `pytest` passes.
    - _Requirements: 3.1, 6.13, 7.11, 8.11, 10.1, 10.13, 10.15, 10.17, 11.7, 11.8_

  - [ ] 16.2 Write the README
    - Create `README.md` with: what Pawleen is; setup (Python version, venv, `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill it in); how to run (`python -m app.main`, and the dev-only `USE_FAKE_AGENTS=1`); all environment variables in a table; how to run the tests (`pytest -q`); the Tailwind rebuild note from the design (`pip install -r requirements-dev.txt` then `tailwindcss -i tailwind/input.css -o static/css/tailwind.css --minify`, then commit the output, and the `TAILWINDCSS_VERSION` pin); the privacy line; the OpenAI findings summary with a link to `docs/openai-findings.md`; and the Render deployment section (task 16.3).
    - Add a "How Kiro was used" section: the spec (requirements, design, tasks) in `.kiro/specs/pawleen-photo-booth/`, the secret-scanning hook in `.kiro/hooks/` and `scripts/check_secrets.py`, steering files if any were added (say so only if they exist), and how tasks were run one at a time. Include the optional three-line `.git/hooks/pre-commit` example that runs `scripts/check_secrets.py`, only as a note for terminal commits.
    - Add a test in `tests/test_static_assets.py` that `README.md` mentions the Tailwind build command and `.env.example`.
    - `pytest` passes.
    - _Requirements: 14.7, 14.10, 13.7, 13.9, 16.5_

  - [ ] 16.3 Add Render deployment files and notes
    - Create `render.yaml` (optional blueprint) with one web service: Python runtime, build command `pip install -r requirements.txt`, start command `python -m app.main`, health check path `/health`, a single instance, and all variable names from `.env.example` with `sync: false` for secrets (`OPENAI_API_KEY`, `JUDGE_PASS`) so no secret is stored in the file. Add the same manual steps to the README (create the web service from the repo, set the environment variables in the Environment tab, set the health check path, keep one instance because counters are in memory).
    - Add a test that `render.yaml` parses, has no `sk-` value, uses `/health`, and its start command equals the README start command.
    - `pytest` passes.
    - _Requirements: 14.1, 14.4, 14.7, 14.8, 13.7_

  - [ ] 16.4 Add the post-deploy smoke test script
    - Create `scripts/smoke_test.py` that takes the base URL and an optional judge pass: it checks `/health`, loads `/` and an unknown path (expects the 404 page), calls `/api/usage`, validates the judge pass through `/api/judge` when one is given (never printing the pass), and optionally runs one real summon through the stream when `--summon sample.jpg` is given, printing only event names and the final status.
    - Add a test of the script's helper functions with `httpx` against the fake-agent app.
    - `pytest` passes.
    - _Requirements: 10.13, 11.6, 14.8, 14.2_

- [ ] 17. Final checkpoint - Deploy and smoke test
  - Run `pytest` and make sure it passes.
  - Deploy to Render (blueprint or manual steps from the README) with the real environment variables. Confirm the health check turns green.
  - Run `python scripts/smoke_test.py https://<your-service>.onrender.com --judge-pass <your pass> --summon sample.jpg`, then open the site on your phone and make one real summon with the judge pass.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property tests and can be skipped for a faster MVP. Each logic task still includes its own example tests.
- No task touches real OpenAI until task 12. Everything before it runs on fake agents at zero cost.
- Browser tasks have manual checks because the project has no Node.js test runner by design.
- Each task lists the requirements it covers, so every requirement from 1 to 16 is traceable to at least one task.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "2.3", "2.5", "4.1", "4.3"] },
    { "id": 2, "tasks": ["2.2", "2.4", "2.6", "3.1", "3.5", "4.2", "4.4", "5.1", "6.2"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.6", "3.7", "5.2", "6.1", "6.3"] },
    { "id": 4, "tasks": ["5.3", "5.4", "5.5", "5.6", "6.4"] },
    { "id": 5, "tasks": ["6.5"] },
    { "id": 6, "tasks": ["6.6", "6.7"] },
    { "id": 7, "tasks": ["8.1", "8.4"] },
    { "id": 8, "tasks": ["8.2"] },
    { "id": 9, "tasks": ["8.3"] },
    { "id": 10, "tasks": ["8.5"] },
    { "id": 11, "tasks": ["8.6"] },
    { "id": 12, "tasks": ["8.7"] },
    { "id": 13, "tasks": ["10.1"] },
    { "id": 14, "tasks": ["10.2"] },
    { "id": 15, "tasks": ["10.3"] },
    { "id": 16, "tasks": ["10.4"] },
    { "id": 17, "tasks": ["12.1"] },
    { "id": 18, "tasks": ["12.2", "12.3", "12.4"] },
    { "id": 19, "tasks": ["12.5", "12.6", "12.7"] },
    { "id": 20, "tasks": ["12.8"] },
    { "id": 21, "tasks": ["14.1"] },
    { "id": 22, "tasks": ["14.2"] },
    { "id": 23, "tasks": ["14.3"] },
    { "id": 24, "tasks": ["14.4"] },
    { "id": 25, "tasks": ["16.1", "16.2", "16.3", "16.4"] }
  ]
}
```
