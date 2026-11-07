# Purpose

**Kind:** image → text (OCR)

**Group:** OCR

**Tags:** `cpu`

| | |
|---|---|
| Input | One PNG, JPEG or WebP image (already cropped to a region). Options: mode (`fast`/`accurate`), timeout. |
| Output | JSON: text, confidence, mode, model fingerprint. |
| Runs on | CPU (Tesseract LSTM, English models). |

**Use for:** classic OCR of clean printed text. Model half of `ToolServices/Lens`.
**Not for:** region cutting, layout or multi-page parsing (see `SGLangModel`), handwriting.
