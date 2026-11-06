# Deploying TesseractModel

TesseractModel is one HTTP service (port 9260). It runs as `tesseract` replicas behind an nginx load balancer,
`tess_lb`. Callers use `http://<host>:9260`; they never reach a replica directly.

## Requirements

- Docker with Compose v2 (the image installs the `tesseract-ocr` package).
- CPU only. A few hundred MB of RAM per replica while recognizing; no model is held in memory.
- Network access once, to download the two model files (about 20 MB) from GitHub (`tesseract-ocr/tessdata_fast` and
  `tessdata_best`).

## Settings

In `.env` next to `docker-compose.yml`:

| Variable | Default | Effect |
|---|---|---|
| `TESS_REPLICAS` | `1` | Number of `tesseract` containers. Read by Compose. |
| `TESS_MEM_LIMIT` | `0` (no cap) | RAM cap per container, for example `1g`. An out-of-memory kill then stays in the container instead of starving the host. Read by Compose. |
| `TESS_PORT` | `9260` | Host port `tess_lb` publishes. |
| `TESS_ADMIN_PASSWORD` | empty | Password for `/admin/`. When set, every call except `/health` must send a token as `X-Internal-Token`. Empty = no auth. |
| `TESS_NUM_THREAD` | Tesseract decides | Starting value for the CPU threads card (`OMP_THREAD_LIMIT`); a value saved on `/admin/` wins. Applies live. With *Recognitions at once* above 1, use 1 to 2. |

On the **Settings** card of `/admin/` (saved in `settings.json` beside the tokens, shared by all replicas; a saved
value beats the environment variable named in brackets): update check hours (`TESS_UPDATE_CHECK_HOURS`, 6),
in-flight cap (`TESS_MAX_INFLIGHT`, 0 = 4), answers kept per replica (`TESS_CACHE_SIZE`, 256, 0 = off), largest image
(`TESS_MAX_UPLOAD_MB`, 10), pixel limit (`TESS_MAX_PIXELS`, 16,000,000), time limit per call (`TESS_TIMEOUT_S`, 110),
recognitions at once (`TESS_CONCURRENCY`, 2, restart) and read files at start (`TESS_WARM`, restart). Compose does not pass these; add the variable
under `environment:` of `tesseract` to use one as a starting value.

## Start

```bash
docker compose up -d --build
curl http://127.0.0.1:9260/health
```

`"ready"` stays `false` until the model files are installed: open `/admin/`, sign in, and press **Download new weights**
on the Updates card once. The files go into the `models` volume, shared by all replicas.

## Scaling

```bash
TESS_REPLICAS=3 docker compose up -d --build
docker compose restart tess_lb
```

The restart is needed because nginx resolves replica addresses once at start.

## Updating the model files

The **Updates** card compares the installed files with the digests pinned in this release. **Download new weights**
installs what is missing or different, checking the SHA-256 first; every replica forgets its kept answers within a few
seconds. A newer upstream model needs a new release: change `WEIGHTS` in `src/engine.py`, then
`docker compose up -d --build` and `docker compose restart tess_lb`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ready` is `false` | The model files are not installed (use the Updates card), or the Tesseract program is missing (native runs: set `TESSERACT_CMD`). |
| 503 on `/v1/ocr` | The mode's model file is missing; download it from the Updates card. |
| 401 "Invalid token" | The caller sends no token, or a revoked one. |
| 422 on `/v1/ocr` | An empty body, an image that cannot be decoded or has too many pixels, an unknown mode, or an unknown query option. |
| 413 | The image is larger than *Largest image*. |
| 429 | Over the token's rate limit, or too many calls waiting. |
| Slow answers | Lower *Recognitions at once* or CPU threads so the processes do not fight for cores; use `mode=fast`. |
| nginx 502 after scaling | `tess_lb` not restarted after the replica count changed. |

## Releasing

A plain publish (`tools\deploy.bat` option 1) only updates the `live` branch. For a release set `VERSION` (and
`pyproject.toml` to the same number), commit, then run `tools\deploy.bat` option R or
`py tools\publish_live.py --release`. `tools\make_zip.bat` then builds `zip_versions\TesseractModel-<VERSION>.zip`.

## Verify with Try it

After deployment, open `/admin/` and use **Try it** with a public service token to exercise the deployed public route. It
uses normal scope, admission/rate limits and cache behavior, so busy or unauthorized requests remain visible as HTTP
errors. Deploy the complete `web/` directory, including `playground.js`. See
[the web UI guide](docs/guide-web-ui.md#try-it-send-a-real-request) for limits and token handling.
