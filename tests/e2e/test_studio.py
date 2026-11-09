"""Browser journeys using generated media and real MP4 rendering."""

from __future__ import annotations

import threading
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf
from werkzeug.serving import make_server

playwright = pytest.importorskip("playwright.sync_api")

from yt2karaoke.pipeline import run
from yt2karaoke.player.app import create_app
from yt2karaoke.transcriber import LyricLine, LyricWord


@pytest.fixture
def studio(tmp_path):
    t = np.arange(32000) / 16000
    instrumental, vocals, source = (tmp_path / name for name in ("instrumental.wav", "vocals.wav", "source.wav"))
    backing = np.sin(2 * np.pi * 220 * t) * 0.2
    voice = np.sin(2 * np.pi * 880 * t) * 0.2
    sf.write(instrumental, backing, 16000)
    sf.write(vocals, voice, 16000)
    sf.write(source, backing + voice, 16000)
    lyrics = [LyricLine("Original test", 0.2, 1.8, [
        LyricWord("Original", 0.2, 0.8), LyricWord("test", 1.0, 1.8),
    ])]

    def render(config, **kwargs):
        config.video_width = 384
        config.video_height = 216
        config.font_size = 28
        config.fps = 8
        return run(config, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch("yt2karaoke.downloader.get_video_info", return_value={"title": "Original test"}))
        stack.enter_context(patch("yt2karaoke.downloader.download_audio", return_value=source))
        stack.enter_context(patch("yt2karaoke.separator.separate", return_value={
            "instrumental": instrumental, "vocals": vocals,
        }))
        stack.enter_context(patch("yt2karaoke.transcriber.transcribe", return_value=lyrics))
        stack.enter_context(patch("yt2karaoke.player.app.run_pipeline", side_effect=render))
        app, _ = create_app(tmp_path / "output", whisper_model="tiny")
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}", source, tmp_path
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.extensions["song_queue"].stop_worker()


@pytest.fixture
def browser_page(studio):
    with playwright.sync_playwright() as integration:
        browser = integration.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(studio[0])
        page.wait_for_load_state("networkidle")
        yield page, errors
        browser.close()


def add_song(page, title="Original test"):
    page.get_by_label("YouTube URL").fill("https://youtube.com/watch?v=synthetic")
    page.get_by_text("Optional settings", exact=True).click()
    page.get_by_label("Song title").fill(title)
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("button", name=f"Play {title}", exact=True).wait_for(timeout=30000)


def test_initial_studio_and_keyboard_mix(browser_page):
    page, errors = browser_page
    page.get_by_text("Live studio", exact=True).wait_for()
    assert page.get_by_role("heading", name="Make room for your voice.").is_visible()
    assert page.get_by_role("radio", name="YouTube link", exact=True).is_checked()
    assert not page.get_by_role("checkbox", name="Add original vocals").is_checked()
    slider = page.get_by_role("slider", name="Original vocals", exact=True)
    assert slider.is_disabled()
    checkbox = page.get_by_role("checkbox", name="Add original vocals")
    checkbox.focus()
    checkbox.press("Space")
    assert slider.is_enabled()
    slider.focus()
    slider.press("End")
    assert slider.input_value() == "100"
    page.get_by_role("button", name="Instrumental, 0% vocals").click()
    assert slider.is_disabled()
    assert not errors


def test_download_instrumental_and_separate_vocal_mix(browser_page, studio):
    page, errors = browser_page
    add_song(page)
    instrumental_link = page.get_by_role("link", name="Download instrumental MP4", exact=True)
    with page.expect_download() as pending:
        instrumental_link.click()
    original = pending.value
    original.save_as(studio[2] / "instrumental.mp4")
    assert original.suggested_filename.endswith("_instrumental.mp4")
    page.get_by_role("button", name="Light guide, 25% vocals").click()
    page.get_by_role("button", name="Create vocal mix", exact=True).click()
    mix_link = page.get_by_role("link", name="Download 25% vocal mix", exact=True)
    mix_link.wait_for(timeout=30000)
    with page.expect_download() as pending:
        mix_link.click()
    pending.value.save_as(studio[2] / "vocal-mix.mp4")
    assert pending.value.suggested_filename.endswith("_vocals_25pct.mp4")
    assert instrumental_link.get_attribute("href").endswith("vocals=0&download=1")
    page.get_by_text("View synced lyrics", exact=True).click()
    assert page.get_by_role("button", name="Seek to Original test").is_visible()
    page.get_by_role("button", name="Play song", exact=True).click()
    page.wait_for_function("document.querySelector('video').currentTime > 0.2")
    page.get_by_role("button", name="Pause song", exact=True).click()
    assert not errors


def test_local_upload_journey(browser_page, studio):
    page, errors = browser_page
    page.get_by_role("radio", name="Local file", exact=True).check()
    page.get_by_label("Audio or video file").set_input_files(studio[1])
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("button", name="Play source", exact=True).wait_for(timeout=30000)
    assert page.get_by_role("link", name="Download instrumental MP4", exact=True).is_visible()
    assert not errors


def test_validation_failure_and_recovery(browser_page):
    page, errors = browser_page
    page.get_by_label("YouTube URL").fill("https://example.com/not-a-song")
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("alert").filter(has_text="Use a YouTube").wait_for()
    assert page.get_by_role("button", name="Add to queue", exact=True).is_enabled()
    page.get_by_label("YouTube URL").fill("https://youtube.com/watch?v=synthetic")
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("button", name="Play Original test", exact=True).wait_for(timeout=30000)
    assert not errors


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_responsive_layout(browser_page, width):
    page, errors = browser_page
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.get_by_role("button", name="Add to queue", exact=True).is_visible()
    assert not errors


def test_titles_are_text_not_html(browser_page):
    page, errors = browser_page
    title = '<img src=x onerror="window.injected=true">'
    add_song(page, title)
    assert page.get_by_role("button", name=f"Play {title}", exact=True).is_visible()
    assert page.evaluate("window.injected === undefined")
    assert not errors
