import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import settings
from app import create_app
from conftest import IMAGE, make_engine, png
from engine import EngineError
from options import SETTINGS
from tokens import TokenStore

URL = "/v1/ocr"


def client(engine=None, admin_password=None, **options):
    return TestClient(create_app(engine or make_engine(), admin_password, **options))


def post(c, query="", image=IMAGE, **kwargs):
    return c.post(URL + query, content=image, **kwargs)


def test_each_project_gets_its_own_revocable_token(tmp_path):
    c = client(admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    admin = {"X-Internal-Token": "admin"}
    assert post(c).status_code == 401 and c.get("/v1/modes").status_code == 401
    made = c.post("/admin/tokens", json={"name": "lens", "rate": 1}, headers=admin).json()
    use = {"X-Internal-Token": made["token"]}
    assert made["token"].startswith("tess_") and post(c, headers=use).status_code == 200
    assert post(c, headers=use).status_code == 429  # one call a minute
    assert c.delete(f"/admin/tokens/{made['id']}", headers=admin).status_code == 200
    assert post(c, headers=use).status_code == 401
    assert c.get("/health").status_code == 200  # no token needed


def test_threads_apply_now_and_are_saved(tmp_path):
    engine = make_engine()
    c = client(engine, "admin", tokens=TokenStore(tmp_path / "t.json"))
    admin = {"X-Internal-Token": "admin"}
    assert c.put("/admin/threads", json={"num_thread": 0}, headers=admin).status_code == 422
    assert c.put("/admin/threads", json={"num_thread": 3}, headers=admin).json() == {"num_thread": 3}
    assert engine.num_thread == 3 and c.get("/health").json()["num_thread"] == 3
    assert settings.load(tmp_path / "settings.json")["num_thread"] == 3


def test_settings_are_admin_only_checked_and_apply_live(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    c = client(admin_password="admin", tokens=store, config=config)
    admin = {"X-Internal-Token": "admin"}
    assert c.get("/admin/settings").status_code == 401
    assert c.put("/admin/settings", json={"values": {"max_inflight": -1}}, headers=admin).status_code == 422
    assert c.put("/admin/settings", json={"values": {"max_inflight": 7, "max_pixels": 50}}, headers=admin).status_code == 200
    saved = {item["key"]: item for item in c.get("/admin/settings", headers=admin).json()["settings"]}
    assert saved["max_inflight"]["value"] == 7
    use = {"X-Internal-Token": c.post("/admin/tokens", json={"name": "p"}, headers=admin).json()["token"]}
    assert post(c, headers=use).status_code == 422  # the new pixel limit applies at once (an 8x8 image has 64 pixels)
    assert client(admin_password="admin").put("/admin/settings", json={"values": {}}, headers=admin).status_code == 409


def test_what_another_replica_saved_reaches_this_one(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    engine = make_engine()
    with TestClient(create_app(engine, "admin", tokens=store, config=config)):
        settings.save(store.settings_path, num_thread=5)
        for _ in range(300):  # the loop looks every second
            if engine.num_thread == 5:
                break
            time.sleep(0.02)
    assert engine.num_thread == 5


def test_health_says_whether_both_model_files_are_installed():
    assert client(make_engine()).get("/health").json()["ready"] is True
    assert client(make_engine(models=("fast",))).get("/health").json()["ready"] is False


def test_startup_warm_up_never_stops_the_service():
    with TestClient(create_app(make_engine(), warm=True)) as c:
        assert c.get("/health").status_code == 200
    with TestClient(create_app(make_engine(models=()), warm=True)) as c:
        assert c.get("/health").json()["ready"] is False


def test_main_builds_the_engine_from_settings(monkeypatch, tmp_path):
    import app as module

    monkeypatch.setenv("SERVICE_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("SERVICE_NUM_THREAD", "2")
    monkeypatch.setenv("SERVICE_PORT", "9999")
    seen, started = [], {}
    monkeypatch.setattr(module.TesseractEngine, "num_thread", property(lambda self: None, lambda self, count: seen.append(count)))
    monkeypatch.setattr("uvicorn.Server.run", lambda self: started.update(app=self.config.app, host=self.config.host, port=self.config.port))
    module.main()
    assert started["port"] == 9999 and started["host"] == "127.0.0.1" and seen == [2]


def test_modes_lists_what_can_answer_with_fingerprints():
    body = client(make_engine(models=("fast",))).get("/v1/modes").json()
    assert body["default"] == "accurate"
    assert body["modes"]["fast"]["available"] is True and body["modes"]["fast"]["fingerprint"].startswith("tesseract-tsv-v1|fast|")
    assert body["modes"]["accurate"] == {"available": False, "fingerprint": None}


def test_ocr_returns_text_confidence_mode_and_fingerprint():
    engine = make_engine()
    body = post(client(engine)).json()
    assert body["text"] == "Hello world" and body["confidence"] == 91.5 and body["mode"] == "accurate"
    assert body["fingerprint"] == engine.fingerprint("accurate") and body["model"] == "tesseract" and "duration_ms" in body


def test_the_mode_and_the_callers_timeout_reach_the_runner():
    engine = make_engine()
    c = client(engine)
    post(c, "?mode=fast&timeout=7")
    call = engine.runner.calls[-1]
    assert call["folder"] == "fast" and call["timeout"] == 7
    assert post(c, "?timeout=100000").status_code == 422  # over the cap
    assert len(engine.runner.calls) == 1


@pytest.mark.parametrize("query", ["?mode=turbo", "?timeout=0", "?stream=true", "?mode=fast&extra=1"])
def test_options_are_validated(query):
    assert post(client(), query).status_code == 422


def test_bad_bodies_are_refused_before_recognition():
    engine = make_engine()
    c = client(engine)
    assert post(c, image=b"").status_code == 422
    assert post(c, image=b"not an image").status_code == 422
    assert engine.runner.calls == []


def test_an_image_over_the_byte_limit_is_a_413():
    assert post(client(make_engine()), image=b"\0" * (10 * 1024 * 1024 + 1)).status_code == 413


@pytest.mark.parametrize("failure,status", [(EngineError("bad", 400), 422), (EngineError("gone", 503), 503), (EngineError("broken", 500), 500)])
def test_engine_failures_map_to_http_errors(failure, status):
    assert post(client(make_engine(fail=failure))).status_code == status


def test_model_errors_never_leak_their_text():
    reply = post(client(make_engine(fail=RuntimeError("failed at /secret/path"))))
    assert reply.status_code == 500 and "secret" not in reply.text


def test_the_in_flight_cap_answers_429_with_retry_after():
    async def run():
        engine = make_engine()
        real = engine.recognize

        async def slow(*args, **kwargs):
            await asyncio.sleep(0.2)
            return await real(*args, **kwargs)

        engine.recognize = slow
        app = create_app(engine, max_inflight=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
            first = asyncio.create_task(http.post(URL, content=IMAGE))
            await asyncio.sleep(0.05)
            second = await http.post(URL, content=IMAGE)
            assert second.status_code == 429 and second.headers["Retry-After"] == "5"
            assert (await first).status_code == 200

    asyncio.run(run())


def test_the_same_image_and_mode_are_answered_from_the_cache():
    engine = make_engine()
    c = client(engine, cache_size=4)
    first, second = post(c), post(c)
    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("miss", "hit")
    assert first.json()["text"] == second.json()["text"] and len(engine.runner.calls) == 1
    post(c, "?mode=fast")  # another mode is another answer
    post(c, image=png(9, 9))
    assert len(engine.runner.calls) == 3
    off = client(make_engine(), cache_size=0)
    assert [post(off).headers["X-Cache"] for _ in range(2)] == ["miss", "miss"]


def test_new_weights_empty_the_cache():
    engine = make_engine()
    c = client(engine, cache_size=4)
    post(c)
    assert post(c).headers["X-Cache"] == "hit"
    asyncio.run(engine.unload())
    assert post(c).headers["X-Cache"] == "miss"


def test_a_kept_answer_is_not_served_without_a_token(tmp_path):
    c = client(admin_password="admin", tokens=TokenStore(tmp_path / "t.json"), cache_size=4)
    made = c.post("/admin/tokens", json={"name": "p"}, headers={"X-Internal-Token": "admin"}).json()
    use = {"X-Internal-Token": made["token"]}
    assert [post(c, headers=use).headers["X-Cache"] for _ in range(2)] == ["miss", "hit"]
    assert post(c).status_code == 401
