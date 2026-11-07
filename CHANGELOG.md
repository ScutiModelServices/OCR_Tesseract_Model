# Changelog

## Unreleased

- `SERVICE_MODELS_DIR` sets where a local (no Docker) run keeps downloaded model weights: `settings.apply_models_dir()` maps it to `HF_HOME` and `OLLAMA_MODELS` at start.
- Docs: `docs/guide-cli.md`, a PowerShell-only way to test the service.

### Breaking: common service environment variables

Service-owned environment variables now use `SERVICE_*`. Old names are no longer read.
Rename old names once in your real `.env`, Compose `environment:` block, and CI/secret settings.

| Old name | New name |
|---|---|
| `TESS_ADMIN_PASSWORD` | `SERVICE_ADMIN_PASSWORD` |
| `TESS_CACHE_SIZE` | `SERVICE_CACHE_SIZE` |
| `TESS_CONCURRENCY` | `SERVICE_CONCURRENCY` |
| `TESS_HOST` | `SERVICE_HOST` |
| `TESS_MAX_INFLIGHT` | `SERVICE_MAX_INFLIGHT` |
| `TESS_MAX_PIXELS` | `SERVICE_MAX_PIXELS` |
| `TESS_MAX_UPLOAD_MB` | `SERVICE_MAX_UPLOAD_MB` |
| `TESS_MEM_LIMIT` | `SERVICE_MEM_LIMIT` |
| `TESS_MODELS_DIR` | `SERVICE_MODELS_DIR` |
| `TESS_NUM_THREAD` | `SERVICE_NUM_THREAD` |
| `TESS_PORT` | `SERVICE_PORT` |
| `TESS_REPLICAS` | `SERVICE_REPLICAS` |
| `TESS_TIMEOUT_S` | `SERVICE_TIMEOUT_S` |
| `TESS_TOKENS_FILE` | `SERVICE_TOKENS_FILE` |
| `TESS_UPDATE_CHECK_HOURS` | `SERVICE_UPDATE_CHECK_HOURS` |
| `TESS_WARM` | `SERVICE_WARM` |
| `TESS_WEB_DIR` | `SERVICE_WEB_DIR` |
| `TESS_WEIGHTS_MARKER` | `SERVICE_WEIGHTS_MARKER` |

- Default HTTP port moves from 9260 to 29261. Update explicit old ports in your real `.env`, saved tool-service `backends.json` connections, and browser/MCP client configurations once. Compose now uses 29261 inside API replicas and nginx; deployments using the old Compose default must recreate containers. A custom host-port override stays in effect until you change it; container ports still move to 29261.

- Renamed `TesseractModel` to `OCR_Tesseract_Model`; Docker project, API image, services, load balancer and volumes now use `ocr_tesseract_model` names. Callers on `citadel_core` connect to `ocr_tesseract_model_lb` at the existing port.
- Docker volume migration: existing volumes with old names are orphaned; renaming does not move data. Stop the old stack before copying; never use `down -v`. The commands below assume the previous default Compose project name; substitute actual volume names if `-p` or `COMPOSE_PROJECT_NAME` overrode it.
  - `tesseract_models` → `ocr_tesseract_model_models`: `docker volume inspect tesseract_models && docker volume create ocr_tesseract_model_models && docker run --rm -v tesseract_models:/from:ro -v ocr_tesseract_model_models:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `tesseract_tokens` → `ocr_tesseract_model_data`: `docker volume inspect tesseract_tokens && docker volume create ocr_tesseract_model_data && docker run --rm -v tesseract_tokens:/from:ro -v ocr_tesseract_model_data:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
- To retain an old volume instead, set its top-level volume definition to `external: true` and `name: <old-volume-name>` in a local Compose override. Rollback: stop the renamed stack, restore the previous checkout and folder name, and restart the old stack with its original volumes; copy back newer data first if the renamed stack accepted writes.

- `run.bat` loads `.env` from the service folder for a local run: it passes `--dotenv`, the service prints which variable names it loaded (never the values), and a real environment variable still wins. A plain `python src/app.py` and Docker never read `.env`.
- Untracked folders now start with `.` or `_`: `zip_versions/` is `_zip_versions/`. A local `voices`, `tem_code` or `zip_versions` folder from an older checkout needs renaming by hand.
- `run.bat` is now a menu (run the service, deploy, build the release ZIP) and `run.bat run|deploy|zip` skips it. `tools/deploy.bat`, `tools/make_zip.bat` and `tools/deploy.local.example.bat` are gone; the local deploy target is `tools/deploy.local.ini` (copy `tools/deploy.local.example.ini`).
- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- First version: Tesseract OCR (`--oem 1`, official English `tessdata_fast` and `tessdata_best`) served on the CPU, with
  the admin page, tokens (rate limit, expiry), metrics, Settings card, update checks, model file downloads, Try it panel
  and answer cache shared with the other model services. Built from STT_Moonshine_Model. It takes over the OCR engine that
  lived inside `AI/ToolServices/Lens`.
- `POST /v1/ocr?mode=fast|accurate&timeout=` takes one PNG, JPEG or WebP crop as the body and returns `text`,
  `confidence`, `mode`, `fingerprint`. `GET /v1/modes` lists what can answer, with fingerprints.
- The model files are two SHA-256 pinned downloads; the Updates card compares them with the installed files.
- Settings: `max_upload_mb`, `max_pixels`, `timeout_s`, `concurrency` (and the shared ones). CPU threads set
  `OMP_THREAD_LIMIT` live.
