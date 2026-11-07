# Deploying OCR_Tesseract_Model

OCR_Tesseract_Model is one HTTP service (port 29261). It runs as `ocr_tesseract_model` replicas behind an nginx load balancer,
`ocr_tesseract_model_lb`. Callers use `http://<host>:29261`; they never reach a replica directly.

## Ways to run it

Each path has its own guide. Pick one.

| Path | Guide |
|---|---|
| Docker Desktop on this PC | [guide-docker-same-device.md](docs/guide-docker-same-device.md) |
| Docker on another always-on machine, published with `run.bat` (Deploy) | [guide-docker-deployment-device.md](docs/guide-docker-deployment-device.md) |
| Directly on Windows, no Docker | [guide-no-docker-same-device.md](docs/guide-no-docker-same-device.md) |

Once it runs, the admin page is covered by [guide-web-ui.md](docs/guide-web-ui.md).
