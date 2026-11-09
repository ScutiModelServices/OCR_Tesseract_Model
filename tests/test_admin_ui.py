"""Browser smoke test for /admin/: sign in, create a token, revoke it.

Needs `pip install playwright && playwright install chromium`; skipped when Playwright is missing.
"""
import socket
import threading
import time

import pytest
import uvicorn

sync_api = pytest.importorskip("playwright.sync_api")

import os
from pathlib import Path

from app import create_app
from conftest import IMAGE, make_engine
from options import SETTINGS
from settings import Config
from updates import Updates

PASSWORD = "secret"


@pytest.fixture
def base_url():
    state = {"downloaded": False}
    engine = make_engine(models=("accurate",))  # the fast file is missing, so the page shows "Starting"

    async def cached():
        return "new" if state["downloaded"] else "old"

    async def latest():
        return "new"

    async def download():
        state.update(downloaded=True)

    updates = Updates("tesseract-ocr/tessdata", cached_sha=cached, remote_sha=latest, download=download, unload=engine.unload,
                      description="Compares the installed files with the digests pinned in this release.",
                      reload_note="Model files installed. Every replica reads the new files on its next request.")
    config = Config(Path(os.environ["SERVICE_TOKENS_FILE"]).with_name("settings.json"), SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    app = create_app(engine, PASSWORD, config=config, updates=updates)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            pytest.fail("Browser test server did not start within 15 seconds")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/admin/"
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def page(base_url):
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(base_url)
        yield page
        browser.close()


def test_wrong_password_is_rejected(page):
    page.fill("#admin", "nope")
    page.click("#signin-button")
    sync_api.expect(page.locator("#login-error")).not_to_be_empty()
    assert page.locator("#dashboard").is_hidden()


def test_create_and_revoke_a_token(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#dashboard")).to_be_visible()
    sync_api.expect(page.locator("#empty")).to_be_visible()
    page.fill("#name", "Garrison")
    page.click("#create-button")
    sync_api.expect(page.locator("#fresh-token")).to_contain_text("tess_")
    row = page.locator("#rows tr")
    sync_api.expect(row).to_contain_text("Garrison")
    sync_api.expect(row.locator('td[data-label="Requests"]')).to_have_text("0")
    row.get_by_role("button", name="Revoke").click()
    page.click("#confirm-revoke")
    sync_api.expect(page.locator("#empty")).to_be_visible()


def test_health_keeps_backend_specific_model_display(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#model-value")).to_have_text("Starting")
    sync_api.expect(page.locator("#health-text")).to_have_text("Starting")


def test_updates_card_checks_and_downloads_without_replica_restart(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#updates-card")).to_be_visible()
    sync_api.expect(page.locator("#updates-description")).to_contain_text("pinned in this release")
    sync_api.expect(page.locator("#update-note")).to_have_text("Not checked yet.")
    page.click("#check-updates")
    sync_api.expect(page.locator("#update-weights")).to_be_visible()
    sync_api.expect(page.locator("#update-list")).to_contain_text("tesseract-ocr/tessdata")
    page.click("#update-weights")
    sync_api.expect(page.locator("#update-note")).to_contain_text("reads the new files on its next request.")
    sync_api.expect(page.locator("#update-weights")).to_be_visible()
    assert "Restart" not in page.locator("#update-note").inner_text()


def test_token_can_be_limited_to_projects(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#dashboard")).to_be_visible()
    page.fill("#name", "Garrison")
    page.fill("#projects", "Bad Name")
    page.click("#create-button")
    sync_api.expect(page.locator("#token-error")).to_contain_text("not valid")
    page.fill("#projects", "app-a, app-b")
    page.click("#create-button")
    sync_api.expect(page.locator("#rows tr")).to_contain_text("Only: app-a, app-b")


def test_token_can_be_edited_and_shows_rate_and_expiry(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#dashboard")).to_be_visible()
    sync_api.expect(page.locator("#project-models-card")).to_be_hidden()  # no project-models tag
    page.fill("#name", "Garrison")
    page.fill("#rate", "5")
    page.fill("#expires", "30")
    page.click("#create-button")
    row = page.locator("#rows tr")
    sync_api.expect(row).to_contain_text("5/min")
    sync_api.expect(row).to_contain_text("Expires")
    row.get_by_role("button", name="Edit").click()
    page.fill("#edit-projects", "app-a")
    page.fill("#edit-rate", "")
    page.click("#save-edit")
    sync_api.expect(row).to_contain_text("Only: app-a")
    sync_api.expect(row).not_to_contain_text("5/min")


def test_settings_can_be_saved_and_reset(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#settings-card")).to_be_visible()
    box = page.locator("#setting-max_inflight")
    sync_api.expect(box).to_have_value("0")
    box.fill("3")
    page.click("#save-settings")
    sync_api.expect(page.locator("#settings-note")).to_have_text("Saved")
    sync_api.expect(page.locator("#setting-max_inflight")).to_have_value("3")
    page.get_by_role("button", name="Reset Calls allowed to wait for the model").click()
    sync_api.expect(page.locator("#setting-max_inflight")).to_have_value("0")


def _open_playground(page):
    """Use separate admin and public credentials."""
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#playground")).to_be_visible()
    made = page.request.post(page.url.rstrip("/") + "/tokens",
                             headers={"X-Internal-Token": PASSWORD}, data={"name": "playground-browser"})
    assert made.status == 200
    token = made.json()["token"]
    page.fill("#pg-token", token)
    return token


def _assert_playground_finished(page, token):
    sync_api.expect(page.locator("#pg-status")).to_contain_text("HTTP 200", timeout=15000)
    sync_api.expect(page.locator("#pg-send")).to_be_enabled(timeout=15000)
    assert "<SERVICE_TOKEN>" in page.locator("#pg-curl").text_content()
    assert token not in page.locator("#pg-curl").text_content()
    assert PASSWORD not in page.locator("#pg-curl").text_content()
    stored = page.evaluate("() => [...Object.values(localStorage), ...Object.values(sessionStorage)]")
    assert not any(token in value for value in stored)


def test_playground_uses_public_route_and_renders_answer(page):
    """Exercise real public auth and the family fake engine."""
    token = _open_playground(page)
    page.set_input_files("#pg-file", {"name": "crop.png", "mimeType": "image/png", "buffer": IMAGE})
    page.click("#pg-send")
    _assert_playground_finished(page, token)
    sync_api.expect(page.locator("#pg-output")).to_contain_text("Hello world")


def test_playground_rejects_oversized_upload_before_request(page):
    _open_playground(page)
    sent = []
    page.on("request", lambda request: sent.append(request.url) if "/v1/ocr" in request.url else None)
    page.set_input_files("#pg-file", {"name": "large.png", "mimeType": "image/png",
                                       "buffer": b"\0" * (10 * 1024 * 1024 + 1)})
    page.click("#pg-send")
    sync_api.expect(page.locator("#pg-status")).to_contain_text("10 MiB")
    sync_api.expect(page.locator("#pg-send")).to_be_enabled()
    assert sent == []


def test_connect_card_lists_the_addresses_other_services_can_use(page):
    page.fill("#admin", PASSWORD)
    page.click("#signin-button")
    sync_api.expect(page.locator("#dashboard")).to_be_visible()
    card = page.locator("#connect-card")
    sync_api.expect(card).to_contain_text("The address you opened this page with")
    sync_api.expect(card).to_contain_text("host.docker.internal")
    sync_api.expect(card).to_contain_text("/health")
    port = page.url.split(":")[2].split("/")[0]
    sync_api.expect(card).to_contain_text("http://127.0.0.1:" + port)
