# English model attribution

This service uses unmodified English traineddata files from Tesseract OCR's
official `tessdata_fast` and `tessdata_best` repositories:

- https://github.com/tesseract-ocr/tessdata_fast
- https://github.com/tesseract-ocr/tessdata_best

Upstream distributes these files under Apache License 2.0. The complete license
is included in `MODEL-LICENSE.txt` and copied into `/licenses/` in the
Docker image. The accepted SHA-256 hashes are in `WEIGHTS` in `src/engine.py`.

The Tesseract program is installed by the Docker image (the `tesseract-ocr` package) or by the host; their package-provided license notices remain with those files.
