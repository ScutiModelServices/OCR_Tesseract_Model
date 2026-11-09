# OCR_Tesseract_Model: Docker Desktop on this PC

Run Tesseract on the CPU in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements

- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- A few hundred MB of RAM **per replica** while recognizing. Keep `SERVICE_REPLICAS=1` on a PC. Docker Desktop on Windows caps its engine at about half of your RAM unless you raise it in `.wslconfig`.
- Network access once, to download the two model files (about 20 MB) from GitHub (`tesseract-ocr/tessdata_fast` and
  `tessdata_best`).
- CPU only. No model is held in memory.

## Steps

1. Configure. In `OCR_Tesseract_Model/`:
   ```bash
   cp .env.example .env
   ```
   Set `SERVICE_ADMIN_PASSWORD` (empty = no auth and no admin page, fine for a local test). Leave `SERVICE_PORT=29261`. Leave `SERVICE_REPLICAS=1`.
2. Start:
   ```bash
   docker compose --env-file .env.compose up -d --build
   ```
   After the first start, open `/admin/` and press **Download new weights** (about 20 MB into the `ocr_tesseract_model_models` volume). `ocr_tesseract_model_lb` starts only after the service is healthy
   (up to 300 s grace). Watch with `docker compose ps` and `docker compose logs -f ocr_tesseract_model`.
3. Check:
   ```bash
   curl http://127.0.0.1:29261/health
   ```
   `ready` is `false` until both model files are installed, then `true`.
4. Open the admin page: `http://127.0.0.1:29261/admin/` (see [guide-web-ui.md](guide-web-ui.md)) and make a token for each caller.
5. Try a call:
   ```bash
   curl -X POST "http://127.0.0.1:29261/v1/ocr?mode=fast" -H "X-Internal-Token: tess_..." -H "Content-Type: image/png" --data-binary @crop.png
   ```
   Expect a JSON answer.
6. Callers connect to the published port. The caller holds the URL and token:
   - Caller on the host: `http://127.0.0.1:29261`.
   - Caller in another Docker stack on the same host: `http://host.docker.internal:29261`.

## Settings

In `.env.compose` next to `docker-compose.yml` (start with `docker compose --env-file .env.compose up -d --build`):

| Variable | Default | Effect |
|---|---|---|
| `SERVICE_REPLICAS` | `1` | Number of `ocr_tesseract_model` containers. Read by Compose. |
| `SERVICE_MEM_LIMIT` | `0` (no cap) | RAM cap per container, for example `1g`. An out-of-memory kill then stays in the container instead of starving the host. Read by Compose. |
| `SERVICE_PORT` | `29261` | Host port `ocr_tesseract_model_lb` publishes. |
| `SERVICE_ADMIN_PASSWORD` | empty | Password for `/admin/`. When set, every call except `/health` must send a token as `X-Internal-Token`. Empty = no auth. |
| `SERVICE_NUM_THREAD` | Tesseract decides | Starting value for the CPU threads card (`OMP_THREAD_LIMIT`); a value saved on `/admin/` wins. Applies live. With *Recognitions at once* above 1, use 1 to 2. |

On the **Settings** card of `/admin/` (saved in `settings.json` beside the tokens, shared by all replicas; a saved
value beats the environment variable named in brackets): update check hours (`SERVICE_UPDATE_CHECK_HOURS`, 6),
in-flight cap (`SERVICE_MAX_INFLIGHT`, 0 = 4), answers kept per replica (`SERVICE_CACHE_SIZE`, 256, 0 = off), largest image
(`SERVICE_MAX_UPLOAD_MB`, 10), pixel limit (`SERVICE_MAX_PIXELS`, 16,000,000), time limit per call (`SERVICE_TIMEOUT_S`, 110),
recognitions at once (`SERVICE_CONCURRENCY`, 2, restart) and read files at start (`SERVICE_WARM`, restart). Compose does not pass these; add the variable
under `environment:` of `ocr_tesseract_model` to use one as a starting value.

## Daily use

```bash
docker compose ps          # state
docker compose logs -f ocr_tesseract_model
docker compose down        # stop (the weights volume is kept)
docker compose --env-file .env.compose up -d --build && docker compose restart ocr_tesseract_model_lb   # after a code change
```

## Problems

| Symptom | Fix |
|---|---|
| `address already in use` on 29261 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `SERVICE_PORT`. |
| `/health` shows `ready: false` for minutes | The model files are not installed yet: use the Updates card. Check `docker compose logs -f ocr_tesseract_model`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |
| Container restarts in a loop | Out of RAM. Raise the Docker Desktop memory limit or lower the replica count. |
| `ready` is `false` | The model files are not installed (use the Updates card), or the Tesseract program is missing (native runs: set `TESSERACT_CMD`). |
| 503 on `/v1/ocr` | The mode's model file is missing; download it from the Updates card. |
| 422 on `/v1/ocr` | An empty body, an image that cannot be decoded or has too many pixels, an unknown mode, or an unknown query option. |
| 413 | The image is larger than *Largest image*. |
| 429 | Over the token's rate limit, or too many calls waiting. |
| Slow answers | Lower *Recognitions at once* or CPU threads so the processes do not fight for cores; use `mode=fast`. |
| nginx 502 after scaling | `ocr_tesseract_model_lb` not restarted after the replica count changed. |

The load balancer also joins external `citadel_core` as `ocr_tesseract_model_lb`. Start the Citadel stack first so that network exists; tool services on it use `http://ocr_tesseract_model_lb:29261`. Docker project and API image are `ocr_tesseract_model` and `ocr_tesseract_model:latest`; persistent volumes have explicit `ocr_tesseract_model_*` names. Volume migration and rollback instructions are in [CHANGELOG.md](../CHANGELOG.md).

Before first inference, follow [Downloaded weights](guide-web-ui.md#downloaded-weights): open `/admin/` → Updates → Download. Startup never downloads weights.
