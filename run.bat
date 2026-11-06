@echo off
REM Starts the Tesseract service on port 9260 (syncs .venv with uv on each run). Install Tesseract first (winget install UB-Mannheim.TesseractOCR) and download the model files from the Updates card on /admin/.
REM LABEL: Tesseract Service
REM DESCRIPTION: Shared HTTP service that runs Tesseract OCR on the CPU for every project.

cd /d "%~dp0"

uv sync
if errorlevel 1 (
    echo uv sync failed. Install uv: winget install astral-sh.uv
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

python src/app.py
pause
