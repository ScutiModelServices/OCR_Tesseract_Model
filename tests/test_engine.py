import asyncio
import os

import pytest

import engine as engine_module
from PIL import Image

from conftest import IMAGE, FakeRunner, make_engine, png
from engine import MODES, EngineError, decode_image, summarize_words


def words():
    return {"level": [5, 5, 5, 4], "text": ["Hello", " ", "world", "x"], "conf": ["90", "80", "70", "99"],
            "page_num": [1] * 4, "block_num": [1] * 4, "par_num": [1] * 4, "line_num": [1, 1, 2, 2]}


def test_words_become_lines_and_an_average_confidence():
    assert summarize_words(words()) == ("Hello\nworld", 80.0)


def test_empty_negative_and_nonfinite_rows_are_ignored():
    data = words()
    data["conf"] = ["-1", "80", "nan", "99"]
    assert summarize_words(data) == ("", None)


def test_only_static_png_jpeg_webp_within_the_pixel_limit_decode():
    assert decode_image(IMAGE, 100).size == (8, 8)
    with pytest.raises(EngineError, match="pixels") as big:
        decode_image(png(20, 20), 100)
    assert big.value.status == 400
    for bad in (b"not an image", b""):
        with pytest.raises(EngineError, match="cannot be decoded"):
            decode_image(bad, 100)
    import io
    gif = io.BytesIO()
    Image.new("L", (4, 4)).save(gif, "GIF")
    with pytest.raises(EngineError, match="static PNG"):
        decode_image(gif.getvalue(), 100)


def test_each_mode_reads_its_own_folder_and_a_changed_file_changes_the_fingerprint():
    engine = make_engine()
    fast, accurate = engine.fingerprint("fast"), engine.fingerprint("accurate")
    assert fast != accurate and fast.startswith("tesseract-tsv-v1|fast|")
    reply = asyncio.run(engine.recognize(Image.new("L", (8, 8)), "fast", 5))
    assert reply == {"text": "Hello world", "confidence": 91.5, "mode": "fast", "fingerprint": fast}
    assert engine.runner.calls[0]["folder"] == "fast"
    (engine.directory("fast") / "eng.traineddata").write_bytes(b"changed")
    assert engine.fingerprint("fast") != fast


def test_a_missing_file_or_program_is_a_503_not_a_crash(tmp_path):
    engine = make_engine(models=("fast",))
    assert engine.modes()["accurate"] == {"available": False, "fingerprint": None} and engine.ready is False
    with pytest.raises(EngineError, match="Download") as caught:
        asyncio.run(engine.recognize(Image.new("L", (8, 8)), "accurate", 5))
    assert caught.value.status == 503
    nothing = make_engine(command="no-such-program-xyz")
    assert nothing.ready is False
    with pytest.raises(EngineError, match="not installed"):
        nothing.fingerprint("fast")


@pytest.mark.skipif(os.name != "nt", reason="the installer location is a Windows thing")
def test_the_windows_install_folder_is_used_when_the_program_is_not_on_path(tmp_path, monkeypatch):
    program = tmp_path / "tesseract.exe"
    program.write_bytes(b"")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setattr(engine_module, "WINDOWS_INSTALL", str(program))
    assert engine_module.TesseractEngine(tmp_path / "models").command == str(program)
    assert engine_module.TesseractEngine(tmp_path / "models", command="no-such-program-xyz").command is None  # an explicit name never falls back


def test_an_unknown_mode_is_refused():
    with pytest.raises(EngineError, match="mode must be") as caught:
        asyncio.run(make_engine().recognize(Image.new("L", (8, 8)), "turbo", 5))
    assert caught.value.status == 400


def test_runner_errors_are_logged_and_never_sent():
    engine = make_engine(fail=RuntimeError("crashed at /secret/path"))
    with pytest.raises(EngineError) as caught:
        asyncio.run(engine.recognize(Image.new("L", (8, 8)), "fast", 5))
    assert "secret" not in str(caught.value) and caught.value.status == 500


def test_threads_set_the_limit_for_tesseract_children(monkeypatch):
    import os
    engine = make_engine()
    engine.num_thread = 3
    assert engine.num_thread == 3 and os.environ["OMP_THREAD_LIMIT"] == "3"


def test_the_installed_and_pinned_digests_say_whether_files_are_current():
    engine = make_engine()
    assert asyncio.run(engine.cached_sha()) != asyncio.run(engine.remote_sha())  # fake files are not the pinned ones
    assert make_engine(models=("fast",))._installed() is None


def test_unload_changes_the_generation_here_and_on_a_replica_through_the_marker(tmp_path):
    first, second = make_engine(), make_engine()
    second._marker = first._marker
    second._seen = second._read_marker()
    before = (first.generation, second.generation)
    asyncio.run(first.unload())
    second.sync()
    assert first.generation == before[0] + 1 and second.generation == before[1] + 1


def test_the_default_downloader_replaces_nothing_when_the_checksum_is_wrong(tmp_path, monkeypatch):
    import httpx
    import engine as module

    def handler(request):
        return httpx.Response(200, content=b"not the model")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: httpx.Client(transport=transport).stream(*a, **{x: y for x, y in k.items() if x != "timeout"}))
    (tmp_path / "fast").mkdir()
    (tmp_path / "fast" / "eng.traineddata").write_bytes(b"old")
    with pytest.raises(ValueError, match="Checksum"):
        module.download_weights(tmp_path)
    assert (tmp_path / "fast" / "eng.traineddata").read_bytes() == b"old"
    assert not list((tmp_path / "fast").glob("*.part"))
