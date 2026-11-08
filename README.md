# OCR_Tesseract_Model

The one place Tesseract OCR is served: Tesseract (`--oem 1`, the LSTM engine) with the official English models, on the
CPU. Projects send one image over HTTP and get text and a confidence back. It has the same admin page, tokens, rate
limits, metrics, settings and update checks as the other model services.

It is the model half of `AI/ToolServices/Lens`: Lens keeps image decoding, region cutting, preprocessing, per-user
quota, jobs and its own result cache, and calls this service once per region. Lens finds this service through a saved
connection on its admin page.

## API

| Call | Purpose |
|---|---|
| `POST /v1/ocr` | Body: one PNG, JPEG or WebP image. Query: `mode`, `timeout`. → `{"text", "confidence", "mode", "fingerprint", "model", "duration_ms"}`. |
| `GET /v1/modes` | `{"modes": {"fast": {"available", "fingerprint"}, "accurate": {...}}, "default"}`. |
| `GET /health` | `{"status": "ok", "model", "ready", "num_thread"}`; `ready` is true when the Tesseract program and both model files are there. No token needed. |

**Input.** The body is one static PNG, JPEG or WebP (`image/*` or `application/octet-stream`). The service does not cut
regions: send a crop. An empty body or an image it cannot decode is 422; more pixels than *Most decoded pixels* is 422;
a body over *Largest image* (default 10 MB) is 413.

**Query options.** `mode` is `accurate` (default, `tessdata_best`) or `fast` (`tessdata_fast`). `timeout` is the seconds the
caller can wait; it can only shorten *Time limit per call*. Any other option is refused with 422.

**Result.** `text` keeps the line breaks Tesseract found. `confidence` is the average of the non-empty words (0 to 100),
or `null` when there is no word. `fingerprint` names the engine reading and the model file's SHA-256
(`tesseract-tsv-v1|<mode>|<digest>`): a caller can key its own cache with it, so a changed model never serves old text.

**Cache.** *Answers kept per replica* (`SERVICE_CACHE_SIZE`, default 256, 0 = off) keeps the last answers for the same image
and mode and sends them again without recognizing (`X-Cache: hit`). Recognition is deterministic, so every request is
kept. New model files empty the cache. The cache is per replica, so with N replicas the hit rate is about 1/N.

**Tokens.** A token's "allowed projects" list has no effect here: there is one engine and no project models.

## Model files

Two official files, pinned by SHA-256 in `src/engine.py` (`WEIGHTS`): `tessdata_fast` and `tessdata_best`, `eng.traineddata`
each, kept under `models/fast` and `models/accurate` (Docker: the `ocr_tesseract_model_models` volume at `/models`). They are not
downloaded at start. Press **Download new weights** on the **Updates** card once; it fetches what is missing or different
and checks the digest before it replaces anything. The card compares the installed files with the pinned digests, so a
newer upstream model needs a new release of this service (a code change on purpose). `ready` stays false until both
files are installed.

## Admin page

`/admin/` (password `SERVICE_ADMIN_PASSWORD`): tokens with rate limit and expiry, usage numbers, CPU threads, the
Settings card (update check hours, in-flight cap, answers kept, largest image, pixel limit, time limit, and the restart
options recognitions at once and read files at start) and the Updates card. `/metrics` (admin password) is Prometheus
text per token. `tess_request_seconds` is a histogram of how long each `/v1` call took on the replica that answers.

CPU threads apply live: the value is saved and every replica sets `OMP_THREAD_LIMIT` for the Tesseract processes it starts
next, within about a second. No restart, no reload. Each recognition is its own Tesseract process, so with more than one
at a time (the default is 2) keep the threads at 1 or 2; set it to at most the physical core count divided by
*Recognitions at once*.

## Run

Weights load only from downloaded files. An empty installation still serves `/admin/` and `/health` with `ready: false`; inference returns 503. Open `/admin/` → **Updates** → **Download** before the first inference. Checks run online without downloading; only an admin Download replaces weights and reloads replicas.

```bash
docker compose up -d --build        # http://<host>:29261
```

Then open `/admin/`, create a token for Lens, and press **Download new weights** (about 5 MB for `fast`, 15 MB for
`accurate`). Without Docker: install Tesseract (`winget install UB-Mannheim.TesseractOCR`), then `run.bat` (uv, listens on
`127.0.0.1:29261`; set `TESSERACT_CMD` if the program is not on PATH). See `deployment.md`.

Example:

```bash
curl -X POST "http://127.0.0.1:29261/v1/ocr?mode=fast" -H "X-Internal-Token: tess_..." \
  -H "Content-Type: image/png" --data-binary @crop.png
```

## Tests

```bash
uv sync
uv run pytest
```

The tests use a fake runner and fake model files; none needs the Tesseract program. `tools/smoke.py` runs the real one.

## Limits worth knowing

- English only; no layout analysis (the caller cuts regions), no PDF.
- The rate limit is per replica.
- Model errors are never sent to the caller (they can hold paths): the reply is "Recognition failed or ran out of time. Try a smaller image."
- On Windows, the models folder path must have no spaces (pytesseract 0.3.13 cannot quote it).
- Not yet measured on the deployment machine.

## Try it from the admin page

Open `/admin/` and use **Try it** to call the public API with a service token held only in memory. Runs use normal token
scopes, limits and caches; the panel shows HTTP status, latency, responses, cancellation and a curl equivalent with a
token placeholder. See [the web UI guide](docs/guide-web-ui.md#try-it-send-a-real-request).

Recognize text sends the chosen image as the raw body to `POST /v1/ocr` with the mode as a query option. The browser caps uploads at 10 MiB.

## Documentation

- [Purpose: input, output and what it is for](docs/purpose.md)
- [Deployment](deployment.md)
- [Changelog](CHANGELOG.md)
- [Docker on another machine](docs/guide-docker-deployment-device.md)
- [Docker on this PC](docs/guide-docker-same-device.md)
- [Run without Docker](docs/guide-no-docker-same-device.md)
- [Model attribution](docs/model-notice.md)
- [Test it from the command line](docs/guide-cli.md)
