"""Tesseract (CPU) run as a child process per crop: one image in, text and confidence out.

Two English model files, `fast` (tessdata_fast) and `accurate` (tessdata_best), each its own tessdata folder under the
models folder; the mode picks the folder through `--tessdata-dir`, so a request never changes the process environment.
Recognition is deterministic, so every request can be kept in the answer cache. The weights are two pinned GitHub files
checked by SHA-256 (`WEIGHTS`), which is why the Updates card compares the pinned digests with the installed ones.
`num_thread` sets OMP_THREAD_LIMIT for the Tesseract children (a live setting, no reload).

shortcut: one crop per call (the caller cuts regions); English only; the Windows path rules of pytesseract 0.3.13 apply
(no spaces in the models folder)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import os
import shlex
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MODES = ("fast", "accurate")
DEFAULT_MODE = "accurate"
MAX_MODEL_BYTES = 32 * 1024 * 1024  # the biggest model file we will accept while downloading
PIN = "tesseract-tsv-v1"  # bump when the way text is read from Tesseract's output changes (it keys caches)
WINDOWS_INSTALL = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", "tesseract.exe")  # where `winget install UB-Mannheim.TesseractOCR` puts it

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeightSpec:
    repository: str
    sha256: str


# Official English models, pinned by content. A new upstream release is a code change on purpose.
WEIGHTS = {
    "fast": WeightSpec("tessdata_fast", "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"),
    "accurate": WeightSpec("tessdata_best", "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba"),
}


class EngineError(RuntimeError):
    """The model could not answer. `status` is the HTTP status the service maps it to."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def decode_image(data: bytes, max_pixels: int) -> Any:
    """One static PNG, JPEG or WebP; the size is checked before pixels are allocated."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise EngineError("Send one static PNG, JPEG or WebP image.", 400)
            if image.width * image.height > max_pixels:
                raise EngineError("The image has more pixels than this service allows.", 400)
            image.load()
            return image.copy()
    except EngineError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise EngineError("The image cannot be decoded. Send a valid PNG, JPEG or WebP.", 400) from None


def summarize_words(data: dict) -> tuple[str, float | None]:
    """Keep line breaks and average the confidence of the non-empty words (0 to 100)."""
    lines, words, scores = [], [], []
    previous = None
    for index, value in enumerate(data["text"]):
        word = value.strip()
        score = float(data["conf"][index])
        if data["level"][index] != 5 or not word or not math.isfinite(score) or not 0 <= score <= 100:
            continue
        line = tuple(data[key][index] for key in ("page_num", "block_num", "par_num", "line_num"))
        if previous is not None and previous != line:
            lines.append(" ".join(words))
            words = []
        words.append(word)
        scores.append(score)
        previous = line
    if words:
        lines.append(" ".join(words))
    return "\n".join(lines), sum(scores) / len(scores) if scores else None


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run_tesseract(image: Any, directory: Path, command: str, timeout: float) -> tuple[str, float | None]:
    """Default runner: one pytesseract call with an explicit tessdata folder."""
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = command
    folder = str(directory.resolve())
    if '"' in folder or "\n" in folder or "\r" in folder:
        raise EngineError("Invalid models folder.", 500)
    if os.name == "nt":  # pytesseract 0.3.13 keeps literal quotes on Windows, so spaces cannot be quoted
        if any(character.isspace() for character in folder):
            raise EngineError("On Windows, keep the models folder path free of spaces.", 500)
        argument = folder
    else:
        argument = shlex.quote(folder)
    data = pytesseract.image_to_data(image, lang="eng", config=f"--oem 1 --tessdata-dir {argument}",
                                     output_type=pytesseract.Output.DICT, timeout=max(0.01, timeout))
    return summarize_words(data)


def default_marker(models_dir: Path) -> Path:
    """File in the shared models volume whose content changes when one replica downloads new weights."""
    configured = os.environ.get("SERVICE_WEIGHTS_MARKER")
    return Path(configured) if configured else models_dir / ".tesseract-weights-version"


def download_weights(models_dir: Path) -> None:
    """Install every pinned file that is missing or different, checking the SHA-256 before it replaces anything."""
    import httpx

    for mode, spec in WEIGHTS.items():
        folder = models_dir / mode
        target = folder / "eng.traineddata"
        folder.mkdir(parents=True, exist_ok=True)
        if target.is_file() and file_digest(target) == spec.sha256:
            continue
        part = folder / f"eng.{uuid.uuid4().hex}.part"
        digest, size = hashlib.sha256(), 0
        url = f"https://raw.githubusercontent.com/tesseract-ocr/{spec.repository}/main/eng.traineddata"
        try:
            with httpx.stream("GET", url, timeout=120, follow_redirects=True) as reply, part.open("xb") as out:
                reply.raise_for_status()
                for chunk in reply.iter_bytes(256 * 1024):
                    size += len(chunk)
                    if size > MAX_MODEL_BYTES:
                        raise ValueError("The download is bigger than a model file can be.")
                    digest.update(chunk)
                    out.write(chunk)
            if digest.hexdigest() != spec.sha256:
                raise ValueError(f"Checksum check failed for the {mode} model; the installed file was not replaced.")
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)


class TesseractEngine:
    """`runner`, `downloader` and `command` are injectable for tests. `runner(image, directory, command, timeout)`
    returns (text, confidence)."""

    model = "tesseract"

    def __init__(self, models_dir: Path | str | None = None, *, marker: Path | None = None,
                 command: str | None = None, runner: Callable[..., tuple[str, float | None]] = run_tesseract,
                 downloader: Callable[[Path], None] = download_weights, concurrency: int = 2) -> None:
        self.models_dir = Path(models_dir or os.environ.get("SERVICE_MODELS_DIR") or "models")
        self.command = shutil.which(command or os.environ.get("TESSERACT_CMD") or "tesseract") or (
            None if command or os.name != "nt" else shutil.which(WINDOWS_INSTALL))  # the Windows installer does not add itself to PATH
        self._runner, self._downloader = runner, downloader
        self._marker = marker if marker is not None else default_marker(self.models_dir)
        self._seen = self._read_marker()
        self._threads: int | None = None
        self._stamps: dict[Path, tuple[tuple[int, int], str]] = {}
        self._lock = threading.Lock()
        self._gate = asyncio.Semaphore(concurrency)
        self.generation = 0  # part of the answer cache key; changes whenever the weights change

    def directory(self, mode: str) -> Path:
        return self.models_dir / mode

    @property
    def num_thread(self) -> int | None:
        return self._threads

    @num_thread.setter
    def num_thread(self, count: int) -> None:
        self._threads = count
        os.environ["OMP_THREAD_LIMIT"] = str(count)  # read by every Tesseract child started after this

    @property
    def ready(self) -> bool:
        return bool(self.command) and all(self.available(mode) for mode in MODES)

    def available(self, mode: str) -> bool:
        return bool(self.command) and (self.directory(mode) / "eng.traineddata").is_file()

    async def close(self) -> None:
        return None

    async def warm(self) -> None:
        """Nothing is loaded in this process; this only reads the model files once so the first call is not the first read."""
        await asyncio.to_thread(self.modes)

    def fingerprint(self, mode: str) -> str:
        if not self.command:
            raise EngineError("Tesseract is not installed on this service.", 503)
        path = self.directory(mode) / "eng.traineddata"
        try:
            with self._lock:
                info = path.stat()
                stamp = (info.st_mtime_ns, info.st_size)
                cached = self._stamps.get(path)
                if cached is None or cached[0] != stamp:
                    self._stamps[path] = stamp, file_digest(path)
                digest = self._stamps[path][1]
        except OSError:
            raise EngineError(f"The {mode} model file is missing. Ask an admin to press Download on the Updates card.", 503) from None
        return f"{PIN}|{mode}|{digest}"

    def modes(self) -> dict[str, dict[str, Any]]:
        """Per mode: whether it can answer, and the fingerprint callers use to separate their caches."""
        result: dict[str, dict[str, Any]] = {}
        for mode in MODES:
            ok = self.available(mode)
            result[mode] = {"available": ok, "fingerprint": self.fingerprint(mode) if ok else None}
        return result

    async def recognize(self, image: Any, mode: str, timeout: float) -> dict[str, Any]:
        if mode not in MODES:
            raise EngineError(f"mode must be one of {', '.join(MODES)}", 400)
        async with self._gate:
            def run() -> dict[str, Any]:
                fingerprint = self.fingerprint(mode)
                try:
                    text, confidence = self._runner(image, self.directory(mode), self.command, timeout)
                except EngineError:
                    raise
                except Exception as error:  # Tesseract errors can hold paths: log them, never send them
                    _log.exception("Recognition failed")
                    raise EngineError("Recognition failed or ran out of time. Try a smaller image.", 500) from error
                return {"text": text, "confidence": confidence, "mode": mode, "fingerprint": fingerprint}

            return await asyncio.to_thread(run)

    # Updates: the pinned digests against the installed files, shared by all replicas through one models volume.

    def _installed(self) -> str | None:
        parts = []
        for mode in MODES:
            path = self.directory(mode) / "eng.traineddata"
            try:
                parts.append(f"{mode}:{file_digest(path)[:12]}")
            except OSError:
                return None
        return ",".join(parts)

    async def cached_sha(self) -> str | None:
        return await asyncio.to_thread(self._installed)

    async def remote_sha(self) -> str:
        return ",".join(f"{mode}:{WEIGHTS[mode].sha256[:12]}" for mode in MODES)

    async def pull(self) -> None:
        await asyncio.to_thread(self._downloader, self.models_dir)

    async def unload(self) -> None:
        """Tell the other replicas the files changed; kept answers are dropped everywhere."""
        if self._marker is not None:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._seen = uuid.uuid4().hex
            self._marker.write_text(self._seen, "utf-8")
        self._forget()

    def sync(self) -> None:
        """Called every second: forget kept answers when another replica downloaded new files."""
        current = self._read_marker()
        if current != self._seen:
            self._seen = current
            self._forget()

    def _forget(self) -> None:
        with self._lock:
            self._stamps.clear()
            self.generation += 1

    def _read_marker(self) -> str | None:
        try:
            return self._marker.read_text("utf-8") if self._marker else None
        except OSError:
            return None
