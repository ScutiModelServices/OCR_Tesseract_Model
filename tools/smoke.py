"""Real-model check: reads a PNG, JPEG or WebP (or draws a small test image) and prints text, confidence and timing.
Needs the Tesseract program and the model files (run the service once and use the Updates card, or set SERVICE_MODELS_DIR).
Usage: uv run python tools/smoke.py [image] [fast|accurate]"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine import TesseractEngine, decode_image  # noqa: E402


async def main() -> None:
    from PIL import Image, ImageDraw

    engine = TesseractEngine()
    mode = sys.argv[2] if len(sys.argv) > 2 else "accurate"
    if len(sys.argv) > 1:
        image = decode_image(Path(sys.argv[1]).read_bytes(), 50_000_000)
    else:
        image = Image.new("L", (360, 80), 255)
        ImageDraw.Draw(image).text((20, 30), "Hello from OCR_Tesseract_Model", fill=0)
    print("modes", engine.modes())
    t = time.perf_counter()
    out = await engine.recognize(image, mode, 60)
    print(f"recognize {time.perf_counter() - t:.1f}s confidence {out['confidence']}\n{out['text']!r}")


asyncio.run(main())
