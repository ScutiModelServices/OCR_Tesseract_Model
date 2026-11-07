import io
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from engine import MODES, TesseractEngine


@pytest.fixture(autouse=True)
def _tmp_tokens_file(tmp_path, monkeypatch):
    """Keeps tokens.json and settings.json out of the repo, and a saved setting from leaking into the next test."""
    monkeypatch.setenv("SERVICE_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.delenv("OMP_THREAD_LIMIT", raising=False)


def png(width=8, height=8, color=255) -> bytes:
    stream = io.BytesIO()
    Image.new("L", (width, height), color).save(stream, "PNG")
    return stream.getvalue()


IMAGE = png()


class FakeRunner:
    """Stands in for Tesseract: answers `text` and `confidence`, records every call."""

    def __init__(self, text="Hello world", confidence=91.5, fail=None):
        self.text, self.confidence, self.fail, self.calls = text, confidence, fail, []

    def __call__(self, image, directory, command, timeout):
        self.calls.append({"size": image.size, "folder": directory.name, "timeout": timeout})
        if self.fail:
            raise self.fail
        return self.text, self.confidence


def make_engine(models=MODES, **options):
    """An engine over a temporary models folder holding fake model files for `models`, with a FakeRunner at `.runner`."""
    folder = Path(tempfile.mkdtemp())
    for mode in models:
        (folder / mode).mkdir()
        (folder / mode / "eng.traineddata").write_bytes(mode.encode() * 10)
    runner = options.pop("runner", None) or FakeRunner(**{k: options.pop(k) for k in ("text", "confidence", "fail") if k in options})
    options.setdefault("command", sys.executable)  # any real program: the runner is fake
    options.setdefault("marker", folder / ".marker")
    options.setdefault("downloader", lambda models_dir: None)
    engine = TesseractEngine(folder, runner=runner, **options)
    engine.runner = runner
    return engine
