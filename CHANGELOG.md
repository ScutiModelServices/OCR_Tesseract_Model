# Changelog

## Unreleased

- First version: Tesseract OCR (`--oem 1`, official English `tessdata_fast` and `tessdata_best`) served on the CPU, with
  the admin page, tokens (rate limit, expiry), metrics, Settings card, update checks, model file downloads, Try it panel
  and answer cache shared with the other model services. Built from STTMoonshineModel. It takes over the OCR engine that
  lived inside `AI/ToolServices/Lens`.
- `POST /v1/ocr?mode=fast|accurate&timeout=` takes one PNG, JPEG or WebP crop as the body and returns `text`,
  `confidence`, `mode`, `fingerprint`. `GET /v1/modes` lists what can answer, with fingerprints.
- The model files are two SHA-256 pinned downloads; the Updates card compares them with the installed files.
- Settings: `max_upload_mb`, `max_pixels`, `timeout_s`, `concurrency` (and the shared ones). CPU threads set
  `OMP_THREAD_LIMIT` live.
