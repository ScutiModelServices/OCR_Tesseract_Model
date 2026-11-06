import asyncio

from conftest import make_engine
from updates import Updates


def updates(downloads=None, **options):
    downloaded = downloads if downloads is not None else []
    engine = make_engine(downloader=lambda folder: downloaded.append(folder), **options)
    return engine, Updates(engine.model, cached_sha=engine.cached_sha, remote_sha=engine.remote_sha,
                           download=engine.pull, unload=engine.unload)


def test_a_check_compares_installed_files_with_the_pinned_digests_without_downloading():
    downloads = []
    _, found = updates(downloads=downloads)
    status = asyncio.run(found.check())
    row = status["weights"][0]
    assert row["update"] is True and row["cached"] != row["latest"] and row["latest"].startswith("fast:")
    assert status["error"] is None and downloads == []


def test_missing_files_are_an_update_with_no_installed_revision():
    _, found = updates(models=())
    row = asyncio.run(found.check())["weights"][0]
    assert row["cached"] is None and row["update"] is True


def test_updating_downloads_then_drops_kept_answers_everywhere():
    downloads = []
    engine, found = updates(downloads=downloads)
    before = engine.generation
    asyncio.run(found.update_weights())
    assert downloads == [engine.models_dir] and engine.generation == before + 1
