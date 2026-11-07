# OCR_Tesseract_Model

Tesseract OCR (`--oem 1`, English `fast` and `accurate` models, CPU) served over HTTP, behind the shared model-service admin page, tokens and settings. Port 9260, env prefix `TESS_`, token prefix `tess_`. The model half of `AI/ToolServices/Lens`: one image crop in, text and confidence out. Built from `STT_Moonshine_Model`.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv`, managed by uv)
- Install: `uv sync` (`winget install astral-sh.uv` if uv is missing)
- Test: `uv run pytest -q` (fake runner and fake model files, no Tesseract program needed). `tests/test_admin_ui.py` needs Playwright and its browser and is skipped without it. On Windows, if uv fails with "cannot move the file to a different disk drive", set `UV_CACHE_DIR` to a folder on the same drive and `UV_LINK_MODE=copy`.
- Run: `run.bat run`, or `uv run python src/app.py` (add `--dotenv` to load `.env`), or `docker compose up -d --build`

## Rules
- Follow the `model-service-parity` skill and `AI/ModelServices/_docs/SHARED-FEATURES.md` (what must match in every model service) and `AI/ModelServices/_docs/SERVICE-SPECIFIC.md` (what differs on purpose). A change to a shared feature goes to every service; a new difference goes into `SERVICE-SPECIFIC.md` in the same change.
- `web/index.html`, `web/playground.js`, `src/tokens.py`, `src/settings.py`, `src/updates.py` and `.dockerignore` are copies shared with the other model services. Change one, copy it to the others, run `python tools/check_sync.py` in each repo.
- Differences from the other services: `POST /v1/ocr` takes one PNG, JPEG or WebP as the body and `mode` (`fast` or `accurate`) and `timeout` as query options (others 422); `GET /v1/modes` lists availability and fingerprints; no streaming, no `trust_remote_code`, no project models, no `temperature`/`max_tokens`; one crop per call (the caller cuts regions); English only.
- Nothing is loaded in this process: each call is a Tesseract child process (`engine.run_tesseract`, pytesseract) with `--tessdata-dir` of the mode's folder, so a request never changes the process environment. `engine.TesseractEngine` takes an injectable `runner`, `downloader` and `command` for tests. `concurrency` (restart setting) is the semaphore of children per replica.
- `num_thread` sets `OMP_THREAD_LIMIT` in this process's environment for the children started next. It is live: no reload, no cache change.
- Model files are two pinned GitHub downloads (`engine.WEIGHTS`, SHA-256 checked before they replace anything), `models/<mode>/eng.traineddata`, in `TESS_MODELS_DIR` (Docker: the `/models` volume). The Updates card compares the pinned digests with the installed files (`cached_sha` is `None` until both exist); a newer upstream model is a code change. `ready` needs the program and both files.
- `fingerprint(mode)` = `tesseract-tsv-v1|<mode>|<sha256 of the file>`, cached by file stamp, returned in every answer and in `/v1/modes`; Lens keys its result cache with it. Bump `PIN` when the way text is read changes.
- Recognition is deterministic, so every request is cached (key = image bytes + mode + engine generation). Model errors are logged and never sent (they can hold paths).
- On Windows the models folder path must not contain spaces (pytesseract 0.3.13 keeps literal quotes).
- Behaviour changes update `README.md`, `deployment.md`, `docs/guide-web-ui.md`, `.env.example` and `CHANGELOG.md` in the same commit.
- Never read or print `.env`, `tokens.json` or `settings.json`.
- Commit with the noreply author email `214214011+scutiii2@users.noreply.github.com` (another address is rejected on push). Push `main`, then run `python tools/publish_live.py`. Build Docker only when the Dockerfile or the dependencies changed.
