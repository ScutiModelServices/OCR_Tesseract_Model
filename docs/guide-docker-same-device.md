# TesseractModel: Docker Desktop on this PC

Run Tesseract on the CPU in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements
- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- A few hundred MB of RAM **per replica**. Keep `TESS_REPLICAS=1` on a PC. Docker Desktop on Windows caps its engine at about half of your RAM unless you raise it in `.wslconfig`.
- Internet once, to download the two model files (about 20 MB) from the Updates card.

## Steps
1. Configure. In `TesseractModel/`:
   ```bash
   cp .env.example .env
   ```
   Set `TESS_ADMIN_PASSWORD` (empty = no auth and no admin page, fine for a local test). Leave `TESS_PORT=9260`. Leave `TESS_REPLICAS=1`.
2. Start:
   ```bash
   docker compose up -d --build
   ```
   After the first start, open `/admin/` and press **Download new weights** (about 20 MB into the `models` volume). `tess_lb` starts only after the service is healthy
   (up to 300 s grace). Watch with `docker compose ps` and `docker compose logs -f tesseract`.
3. Check:
   ```bash
   curl http://127.0.0.1:9260/health
   ```
   `ready` is `false` until both model files are installed, then `true`.
4. Open the admin page: `http://127.0.0.1:9260/admin/` (see [guide-web-ui.md](guide-web-ui.md)) and make a token for each caller.
5. Try a call:
   ```bash
   curl -X POST "http://127.0.0.1:9260/v1/ocr?mode=fast" -H "X-Internal-Token: tess_..." -H "Content-Type: image/png" --data-binary @crop.png
   ```
   Expect a JSON answer.
6. Callers connect to the published port. The caller holds the URL and token:
   - Caller on the host: `http://127.0.0.1:9260`.
   - Caller in another Docker stack on the same host: `http://host.docker.internal:9260`.

## Daily use
```bash
docker compose ps          # state
docker compose logs -f tesseract
docker compose down        # stop (the weights volume is kept)
docker compose up -d --build && docker compose restart tess_lb   # after a code change
```

## Problems
| Symptom | Fix |
|---|---|
| `address already in use` on 9260 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `TESS_PORT`. |
| `/health` shows `ready: false` for minutes | The model files are not installed yet: use the Updates card. Check `docker compose logs -f tesseract`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |

| Container restarts in a loop | Out of RAM. Raise the Docker Desktop memory limit or lower the replica count. |
