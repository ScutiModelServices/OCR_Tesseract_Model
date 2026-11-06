# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV TESS_WEB_DIR=/app/web TESS_TOKENS_FILE=/data/tokens.json TESS_MODELS_DIR=/models PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" TESS_HOST=0.0.0.0
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
COPY web ./web
COPY MODEL-LICENSE.txt MODEL-NOTICE.md /licenses/

EXPOSE 9260
CMD ["python", "src/app.py"]
