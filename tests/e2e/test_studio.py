"""Browser journeys using generated media and real MP4 rendering."""

from __future__ import annotations

import json
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


@pytest.fixture(params=["light", "dark"])
def browser_page(studio, request):
    with playwright.sync_playwright() as integration:
        browser = integration.chromium.launch(headless=True, args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            accept_downloads=True, color_scheme=request.param,
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(studio[0])
        page.wait_for_load_state("networkidle")
        yield page, errors
        context.close()
        browser.close()


def add_song(page, title="Original test", performer=""):
    page.get_by_label("YouTube URL").fill("https://youtube.com/watch?v=synthetic")
    if performer:
        page.get_by_label("Singer / group name", exact=True).fill(performer)
    page.get_by_text("Optional settings", exact=True).click()
    page.get_by_label("Song title").fill(title)
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("button", name=f"Play {title}", exact=True).wait_for(timeout=30000)


def install_audio_probe(page):
    page.evaluate("""() => {
        const connect = AudioNode.prototype.connect;
        AudioNode.prototype.connect = function(destination, ...args) {
            if (destination instanceof AudioDestinationNode) {
                const analyser = this.context.createAnalyser();
                analyser.fftSize = 8192;
                analyser.smoothingTimeConstant = 0;
                connect.call(this, analyser);
                window.testMixAnalyser = analyser;
            }
            return connect.call(this, destination, ...args);
        };
        window.testAudioLevels = () => {
            const analyser = window.testMixAnalyser;
            if (!analyser) return {backing: 0, voice: 0, rms: 0};
            const spectrum = new Float32Array(analyser.frequencyBinCount);
            analyser.getFloatFrequencyData(spectrum);
            const amplitude = frequency => {
                const bin = Math.round(frequency * analyser.fftSize / analyser.context.sampleRate);
                return 10 ** (Math.max(...spectrum.slice(bin - 3, bin + 4)) / 20);
            };
            const samples = new Float32Array(analyser.fftSize);
            analyser.getFloatTimeDomainData(samples);
            return {
                backing: amplitude(220), voice: amplitude(880),
                rms: Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length),
            };
        };
    }""")


def finish_song(page):
    page.wait_for_function("Number.isFinite(document.querySelector('#main-video').duration)")
    page.evaluate("""() => {
        const video = document.querySelector("#main-video");
        video.loop = false;
        video.currentTime = video.duration - 0.05;
    }""")


def expect_theme(page, theme):
    backgrounds = {"light": "#f5f5fa", "dark": "#171722"}
    playwright.expect(page.locator("html")).to_have_attribute("data-theme", theme)
    playwright.expect(page.locator("html")).to_have_css("color-scheme", theme)
    playwright.expect(page.locator('meta[name="theme-color"]')).to_have_attribute(
        "content", backgrounds[theme],
    )
    expected = {"light": "rgb(245, 245, 250)", "dark": "rgb(23, 23, 34)"}
    playwright.expect(page.locator("body")).to_have_css("background-color", expected[theme])


def test_theme_follows_system_and_responds_to_changes(browser_page):
    page, errors = browser_page
    theme = page.get_by_role("combobox", name="Theme", exact=True)
    playwright.expect(theme).to_have_value("system")
    initial = page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches")
    expect_theme(page, "dark" if initial else "light")
    for scheme in ("dark", "light"):
        page.emulate_media(color_scheme=scheme)
        expect_theme(page, scheme)
    assert page.evaluate("localStorage.getItem('yt2karaoke-theme')") is None
    assert not errors


def test_theme_choice_is_keyboard_accessible_and_persists(browser_page):
    page, errors = browser_page
    theme = page.get_by_role("combobox", name="Theme", exact=True)
    theme.focus()
    theme.press("d")
    theme.press("Enter")
    playwright.expect(theme).to_have_value("dark")
    expect_theme(page, "dark")
    page.emulate_media(color_scheme="light")
    expect_theme(page, "dark")
    page.reload(wait_until="networkidle")
    playwright.expect(theme).to_have_value("dark")
    expect_theme(page, "dark")
    theme.select_option("light")
    page.emulate_media(color_scheme="dark")
    expect_theme(page, "light")
    page.reload(wait_until="networkidle")
    playwright.expect(theme).to_have_value("light")
    expect_theme(page, "light")
    theme.select_option("system")
    expect_theme(page, "dark")
    page.emulate_media(color_scheme="light")
    expect_theme(page, "light")
    assert page.evaluate("localStorage.getItem('yt2karaoke-theme')") == "system"
    assert not errors


@pytest.mark.parametrize("preference", ["light", "dark"])
def test_saved_theme_applies_before_the_studio_script(browser_page, preference):
    page, errors = browser_page
    page.evaluate("value => localStorage.setItem('yt2karaoke-theme', value)", preference)
    page.route("**/static/studio.js", lambda route: route.fulfill(
        content_type="application/javascript",
        body="window.themeBeforeStudio = document.documentElement.dataset.theme;",
    ))
    page.reload(wait_until="networkidle")
    assert page.evaluate("window.themeBeforeStudio") == preference
    expect_theme(page, preference)
    playwright.expect(page.get_by_role("combobox", name="Theme", exact=True)).to_have_value(preference)
    assert not errors


def test_theme_preference_syncs_between_tabs(browser_page, studio):
    page, errors = browser_page
    other = page.context.new_page()
    other.on("pageerror", lambda error: errors.append(str(error)))
    try:
        other.goto(studio[0], wait_until="networkidle")
        theme = page.get_by_role("combobox", name="Theme", exact=True)
        other_theme = other.get_by_role("combobox", name="Theme", exact=True)
        theme.select_option("dark")
        expect_theme(other, "dark")
        playwright.expect(other_theme).to_have_value("dark")
        other_theme.select_option("light")
        expect_theme(page, "light")
        playwright.expect(theme).to_have_value("light")
        other.evaluate("localStorage.clear()")
        playwright.expect(theme).to_have_value("system")
        system_dark = page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches")
        expect_theme(page, "dark" if system_dark else "light")
    finally:
        other.close()
    assert not errors


def test_theme_still_works_when_browser_storage_is_blocked(browser_page):
    page, errors = browser_page
    warnings = []
    page.on("console", lambda message: warnings.append(message.text) if message.type == "warning" else None)
    page.add_init_script("""
        Object.defineProperty(window, "localStorage", {
            get() { throw new DOMException("Test storage is blocked", "SecurityError"); }
        });
    """)
    page.reload(wait_until="networkidle")
    theme = page.get_by_role("combobox", name="Theme", exact=True)
    theme.select_option("dark")
    page.emulate_media(color_scheme="light")
    expect_theme(page, "dark")
    playwright.expect(page.get_by_role("alert").filter(
        has_text="Theme changed for this page, but your browser could not save it.",
    )).to_be_visible()
    theme.select_option("system")
    expect_theme(page, "light")
    assert any("Could not read the theme preference" in message for message in warnings)
    assert any("Could not save the theme preference" in message for message in warnings)
    assert not errors


def test_invalid_saved_theme_uses_the_system_preference(browser_page):
    page, errors = browser_page
    page.evaluate("localStorage.setItem('yt2karaoke-theme', 'invalid')")
    page.reload(wait_until="networkidle")
    playwright.expect(page.get_by_role("combobox", name="Theme", exact=True)).to_have_value("system")
    system_dark = page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches")
    expect_theme(page, "dark" if system_dark else "light")
    assert not errors


def test_dark_theme_text_and_controls_have_accessible_contrast(browser_page):
    page, errors = browser_page
    page.get_by_role("combobox", name="Theme", exact=True).select_option("dark")
    playwright.expect(page.get_by_role("button", name="Add to queue", exact=True)).to_have_css(
        "background-color", "rgb(186, 167, 255)",
    )
    pairs = page.evaluate("""() => {
        const colors = (value) => value.match(/[\\d.]+/g).map(Number);
        const pairs = [
            ["body", "body"], [".page-description", "body"],
            [".panel-heading h2", ".preview-card"], [".subtle-tag", ".preview-card"],
            ["#url-input", ".input-wrap"], ["#theme-select", "#theme-select"],
            [".button-primary", ".button-primary"], [".button-mix", ".button-mix"],
            [".mix-presets button[aria-pressed=true]", ".mix-presets button[aria-pressed=true]"],
            [".mix-presets button[aria-pressed=true] span", ".mix-presets button[aria-pressed=true]"],
            [".background-picker label:has(input:checked) small", ".background-picker label:has(input:checked)"],
            [".export-note p > span", ".export-note"],
            [".time-readout", ".player-controls"],
            [".inline-error", ".source-card"], [".error-notice", ".error-notice"],
            [".notice", ".notice"], [".button-download", ".button-download"],
        ];
        return pairs.map(([text, surface]) => ({
            selector: text,
            foreground: colors(getComputedStyle(document.querySelector(text)).color),
            background: colors(getComputedStyle(document.querySelector(surface)).backgroundColor),
            minimum: 4.5,
        })).concat([".input-wrap", ".theme-control select", ".mix-presets button"].map((selector) => {
            const style = getComputedStyle(document.querySelector(selector));
            return {
                selector, foreground: colors(style.borderTopColor),
                background: colors(style.backgroundColor), minimum: 3,
            };
        }));
    }""")

    def luminance(rgb):
        assert len(rgb) == 3, f"Expected an opaque color, got {rgb}"
        channels = [value / 255 for value in rgb]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    for pair in pairs:
        bright, dark = sorted((luminance(pair["foreground"]), luminance(pair["background"])), reverse=True)
        ratio = (bright + 0.05) / (dark + 0.05)
        assert ratio >= pair["minimum"], f'{pair["selector"]}: {ratio:.2f}:1 contrast'
    assert not errors


def test_theme_keeps_the_stage_artwork_unchanged(browser_page):
    page, errors = browser_page
    theme = page.get_by_role("combobox", name="Theme", exact=True)
    stage = page.locator(
        ".empty-stage, .empty-stage h2, .empty-stage h2 span, "
        ".processing-overlay, .processing-overlay p, .processing-spinner, .player-controls",
    )
    styles = """elements => elements.map(element => {
        const style = getComputedStyle(element);
        return [style.color, style.backgroundColor, style.backgroundImage, style.borderTopColor, style.accentColor];
    })"""
    theme.select_option("light")
    light = stage.evaluate_all(styles)
    theme.select_option("dark")
    assert stage.evaluate_all(styles) == light
    assert not errors


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
    page.get_by_text("Vocal mix ready to download.", exact=True).wait_for()
    with page.expect_download() as pending:
        mix_link.click()
    pending.value.save_as(studio[2] / "vocal-mix.mp4")
    assert pending.value.suggested_filename.endswith("_vocals_25pct.mp4")
    assert instrumental_link.get_attribute("href").endswith("vocals=0&download=1")
    assert page.locator("#main-video").get_attribute("src").endswith("vocals=0")
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


def test_original_vocal_slider_changes_live_playback_without_an_export(browser_page):
    page, errors = browser_page
    add_song(page)
    page.get_by_role("button", name="Play song", exact=True).click()
    page.get_by_role("button", name="Light guide, 25% vocals").click()
    page.wait_for_function("""() => {
        const vocals = document.querySelector("#original-vocals");
        return vocals && !vocals.paused && vocals.currentTime > 0;
    }""")
    assert page.locator("#main-video").get_attribute("src").endswith("vocals=0")
    assert page.locator("#original-vocals").get_attribute("src").endswith("/vocals")
    assert not page.get_by_role("link", name="Download 25% vocal mix", exact=True).is_visible()
    playwright.expect(page.locator("#preview-tag")).to_contain_text("25%")
    assert not errors


def test_live_vocal_gain_and_master_volume_are_measured_in_the_audio_output(browser_page):
    page, errors = browser_page
    install_audio_probe(page)
    add_song(page)
    page.evaluate("document.querySelector('#main-video').loop = true")
    page.get_by_role("button", name="Light guide, 25% vocals").click()
    page.get_by_role("button", name="Play song", exact=True).click()
    page.wait_for_function("window.testAudioLevels().voice > 0.005")
    page.wait_for_timeout(250)  # Let the FFT window and gain ramp contain only the selected mix.
    quiet = page.evaluate("window.testAudioLevels()")
    slider = page.get_by_role("slider", name="Original vocals", exact=True)
    slider.focus()
    slider.press("End")
    page.wait_for_function("quiet => window.testAudioLevels().voice > quiet.voice * 3.9", arg=quiet)
    loud = page.evaluate("window.testAudioLevels()")
    assert loud["voice"] / quiet["voice"] == pytest.approx(4, abs=0.35)
    assert loud["backing"] / quiet["backing"] == pytest.approx(1, abs=0.1)
    page.get_by_role("button", name="Instrumental, 0% vocals").click()
    page.wait_for_function("loud => window.testAudioLevels().voice < loud.voice * 0.02", arg=loud)
    assert page.evaluate("window.testAudioLevels().backing") == pytest.approx(loud["backing"], rel=0.1)
    speakers = page.get_by_role("slider", name="Speaker volume", exact=True)
    speakers.focus()
    speakers.press("Home")
    playwright.expect(page.get_by_role("slider", name="Playback volume", exact=True)).to_have_value("0")
    page.wait_for_function("window.testAudioLevels().rms < 0.0001")
    speakers.press("End")
    page.wait_for_function("window.testAudioLevels().rms > 0.05")
    page.get_by_role("button", name="Mute speakers", exact=True).click()
    page.wait_for_function("window.testAudioLevels().rms < 0.0001")
    page.get_by_role("button", name="Unmute speakers", exact=True).click()
    page.wait_for_function("window.testAudioLevels().rms > 0.05")
    backing = page.get_by_role("slider", name="Backing track volume", exact=True)
    backing.focus()
    backing.press("Home")
    page.wait_for_function("window.testAudioLevels().rms < 0.0001")
    assert not errors


def test_microphone_is_opt_in_muted_and_releases_fake_capture(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
        window.testMicTracks = [];
        window.testFilters = [];
        window.testCompressors = [];
        const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async options => {
            const stream = await capture(options);
            window.testMicTracks.push(...stream.getTracks());
            return stream;
        };
        const filter = AudioContext.prototype.createBiquadFilter;
        AudioContext.prototype.createBiquadFilter = function() {
            const node = filter.call(this);
            window.testFilters.push(node);
            return node;
        };
        const compressor = AudioContext.prototype.createDynamicsCompressor;
        AudioContext.prototype.createDynamicsCompressor = function() {
            const node = compressor.call(this);
            window.testCompressors.push(node);
            return node;
        };
        const PitchNode = window.AudioWorkletNode;
        window.AudioWorkletNode = class extends PitchNode {
            constructor(...args) { super(...args); window.testPitch = this; }
        };
    }""")
    assert page.evaluate("window.testMicTracks.length") == 0
    page.get_by_role("button", name="Enable microphone", exact=True).click()
    playwright.expect(page.locator("#mic-status")).to_have_text("Microphone on / muted")
    monitor = page.get_by_role("checkbox", name="Hear my microphone", exact=True)
    assert not monitor.is_checked()
    page.wait_for_function("document.querySelector('#mic-meter').value > 0")
    page.get_by_role("button", name="High pitch", exact=True).click()
    page.wait_for_function("Math.abs(window.testPitch.parameters.get('semitones').value - 7) < 0.1")
    page.get_by_role("button", name="Low pitch", exact=True).click()
    page.wait_for_function("Math.abs(window.testPitch.parameters.get('semitones').value + 7) < 0.1")
    bass = page.get_by_role("slider", name="Bass", exact=True)
    bass.focus()
    bass.press("End")
    page.wait_for_function("Math.abs(window.testFilters.find(node => node.type === 'lowshelf').gain.value - 12) < 0.1")
    compression = page.get_by_role("slider", name="Compression", exact=True)
    compression.focus()
    compression.press("End")
    page.wait_for_function("Math.abs(window.testCompressors.at(-1).threshold.value + 36) < 0.1")
    monitor.check()
    playwright.expect(page.locator("#mic-status")).to_have_text("Microphone on / monitoring")
    page.get_by_role("button", name="Disable microphone", exact=True).click()
    playwright.expect(page.locator("#mic-status")).to_have_text("Microphone off")
    assert page.evaluate("window.testMicTracks.every(track => track.readyState === 'ended')")
    assert monitor.is_disabled()
    page.get_by_role("button", name="Enable microphone", exact=True).click()
    playwright.expect(page.locator("#mic-status")).to_have_text("Microphone on / muted")
    assert not monitor.is_checked()
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
    assert page.evaluate("window.testMicTracks.every(track => track.readyState === 'ended')")
    assert not errors


def test_denied_microphone_permission_is_reported_without_breaking_playback(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
        navigator.mediaDevices.getUserMedia = async () => {
            throw new DOMException("Test permission denied", "NotAllowedError");
        };
    }""")
    page.get_by_role("button", name="Enable microphone", exact=True).click()
    playwright.expect(page.get_by_role("alert").filter(has_text="Allow microphone access")).to_be_visible()
    assert page.get_by_role("button", name="Enable microphone", exact=True).is_enabled()
    add_song(page)
    page.get_by_role("button", name="Play song", exact=True).click()
    page.wait_for_function("document.querySelector('#main-video').currentTime > 0.2")
    assert not errors


def test_speaker_selection_failure_keeps_the_previous_output(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
        navigator.mediaDevices.enumerateDevices = async () => [
            {kind: "audiooutput", deviceId: "test-speakers", label: "Test speakers"},
        ];
        AudioContext.prototype.setSinkId = async () => {
            throw new DOMException("Test speakers unavailable", "NotFoundError");
        };
    }""")
    page.get_by_role("button", name="Refresh devices", exact=True).click()
    speakers = page.get_by_role("combobox", name="Speakers", exact=True)
    speakers.select_option("test-speakers")
    playwright.expect(page.get_by_role("alert").filter(has_text="Speakers could not change")).to_be_visible()
    playwright.expect(speakers).to_have_value("")
    assert not errors


def test_speaker_selection_waits_for_the_device_change(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
        navigator.mediaDevices.enumerateDevices = async () => [
            {kind: "audiooutput", deviceId: "test-speakers", label: "Test speakers"},
        ];
        AudioContext.prototype.setSinkId = () => new Promise(resolve => {
            window.resolveTestSink = resolve;
        });
    }""")
    page.get_by_role("button", name="Refresh devices", exact=True).click()
    speakers = page.get_by_role("combobox", name="Speakers", exact=True)
    speakers.select_option("test-speakers")
    page.wait_for_function("typeof window.resolveTestSink === 'function'")
    assert speakers.is_disabled()
    page.evaluate("window.resolveTestSink()")
    playwright.expect(speakers).to_be_enabled()
    playwright.expect(speakers).to_have_value("test-speakers")
    assert not errors


def test_stage_window_mirrors_video_and_seeks_without_duplicate_audio(browser_page):
    page, errors = browser_page
    add_song(page)
    with page.expect_popup() as pending:
        page.get_by_role("button", name="Open stage window", exact=True).click()
    stage_page = pending.value
    stage_page.on("pageerror", lambda error: errors.append(str(error)))
    stage_page.wait_for_load_state("networkidle")
    page.evaluate("document.querySelector('#main-video').loop = true")
    page.get_by_role("button", name="Play song", exact=True).click()
    stage_page.wait_for_function("!document.querySelector('#stage-video').paused")
    assert stage_page.locator("#stage-video").evaluate("video => video.muted")
    assert stage_page.locator("#stage-video").get_attribute("src") == page.locator("#main-video").get_attribute("src")
    stage_page.reload(wait_until="networkidle")
    stage_page.wait_for_function("!document.querySelector('#stage-video').paused")
    assert page.get_by_role("button", name="Close stage window", exact=True).is_visible()
    page.get_by_role("button", name="Pause song", exact=True).click()
    stage_page.wait_for_function("document.querySelector('#stage-video').paused")
    page.locator("#main-video").evaluate("video => { video.currentTime = 1; }")
    stage_page.wait_for_function("Math.abs(document.querySelector('#stage-video').currentTime - 1) <= 0.12")
    stage_page.get_by_role("button", name="Close stage", exact=True).click()
    playwright.expect(page.get_by_role("button", name="Open stage window", exact=True)).to_be_visible()
    assert not errors


def test_singer_countdown_keeps_the_playing_song_and_names_the_next_singer(browser_page):
    page, errors = browser_page
    add_song(page, "First fixture", "Test solo")
    page.evaluate("document.querySelector('#main-video').loop = true")
    page.get_by_role("button", name="Play song", exact=True).click()
    first_source = page.locator("#main-video").get_attribute("src")
    add_song(page, "Second fixture", "Test duo")
    assert page.locator("#main-video").get_attribute("src") == first_source
    assert page.get_by_role("button", name="Pause song", exact=True).is_visible()
    playwright.expect(page.get_by_role("spinbutton", name="Seconds between songs")).to_have_value("30")
    with page.expect_popup() as pending:
        page.get_by_role("button", name="Open stage window", exact=True).click()
    stage_page = pending.value
    stage_page.on("pageerror", lambda error: errors.append(str(error)))
    stage_page.wait_for_load_state("networkidle")
    page.get_by_role("spinbutton", name="Seconds between songs").fill("2")
    page.get_by_role("spinbutton", name="Seconds between songs").press("Tab")
    page.evaluate("""() => {
        const video = document.querySelector("#main-video");
        video.loop = false;
        video.currentTime = video.duration - 0.1;
    }""")
    playwright.expect(page.locator("#countdown-overlay")).to_be_visible()
    playwright.expect(page.locator("#next-singer")).to_have_text("Test duo")
    playwright.expect(page.locator("#next-song")).to_have_text("Second fixture")
    playwright.expect(stage_page.locator("#stage-next-singer")).to_have_text("Test duo")
    playwright.expect(stage_page.locator("#stage-countdown")).to_be_visible()
    assert page.locator("#main-video").get_attribute("src") == first_source
    page.wait_for_function(
        "first => document.querySelector('#main-video').getAttribute('src') !== first", arg=first_source,
    )
    playwright.expect(page.locator("#now-playing-title")).to_have_text("Second fixture")
    assert not errors


def test_other_singers_can_add_songs_without_taking_over_playback(browser_page, studio):
    page, errors = browser_page
    add_song(page, "Playing fixture", "Test solo")
    page.evaluate("document.querySelector('#main-video').loop = true")
    page.get_by_role("button", name="Play song", exact=True).click()
    first_source = page.locator("#main-video").get_attribute("src")
    guest = page.context.new_page()
    guest.on("pageerror", lambda error: errors.append(str(error)))
    try:
        guest.goto(studio[0], wait_until="networkidle")
        add_song(guest, "Queued fixture", "Test trio")
        playwright.expect(page.get_by_role("list", name="Song queue", exact=True).get_by_role("listitem")).to_have_count(2)
        playwright.expect(page.locator("#queue-list")).to_contain_text("Test trio")
        assert page.locator("#main-video").get_attribute("src") == first_source
        assert not page.locator("#main-video").evaluate("video => video.paused")
        assert guest.locator("#main-video").evaluate("video => video.paused")
        playwright.expect(page.locator(".queue-status").filter(has_text="Playing")).to_have_count(1)
        playwright.expect(guest.locator(".queue-status").filter(has_text="Playing")).to_have_count(0)
    finally:
        guest.close()
    assert not errors


def test_countdown_can_be_held_and_a_removed_next_song_is_not_played(browser_page):
    page, errors = browser_page
    add_song(page, "First fixture", "Test solo")
    add_song(page, "Second fixture", "Test duo")
    page.get_by_role("button", name="Play song", exact=True).click()
    finish_song(page)
    playwright.expect(page.locator("#countdown-overlay")).to_be_visible()
    page.get_by_role("button", name="Remove Second fixture", exact=True).click()
    playwright.expect(page.locator("#countdown-label")).to_have_text("WAITING FOR THE NEXT SONG")
    assert page.get_by_role("button", name="Start now", exact=True).is_disabled()
    add_song(page, "Third fixture", "Test trio")
    playwright.expect(page.locator("#next-singer")).to_have_text("Test trio")
    page.get_by_role("button", name="Hold the stage", exact=True).click()
    playwright.expect(page.locator("#countdown-overlay")).to_be_hidden()
    assert page.locator("#main-video").evaluate("video => video.ended")
    page.get_by_role("button", name="Play Third fixture", exact=True).click()
    playwright.expect(page.locator("#now-playing-title")).to_have_text("Third fixture")
    assert not errors


def test_zero_gap_starts_the_next_song_and_invalid_gaps_are_reported(browser_page):
    page, errors = browser_page
    add_song(page, "First fixture")
    add_song(page, "Second fixture")
    gap = page.get_by_role("spinbutton", name="Seconds between songs")
    gap.fill("-1")
    gap.press("Tab")
    playwright.expect(page.locator("#playback-error")).to_contain_text("still 30 seconds")
    gap.fill("0")
    gap.press("Tab")
    playwright.expect(page.locator("#playback-error")).to_be_hidden()
    page.get_by_role("button", name="Play song", exact=True).click()
    finish_song(page)
    playwright.expect(page.locator("#now-playing-title")).to_have_text("Second fixture")
    playwright.expect(page.locator("#countdown-overlay")).to_be_hidden()
    assert not errors


def test_local_upload_uses_provided_word_timings(browser_page, studio):
    page, errors = browser_page
    page.get_by_role("radio", name="Local file", exact=True).check()
    page.get_by_label("Audio or video file").set_input_files(studio[1])
    page.get_by_text("Optional settings", exact=True).click()
    lyrics = [{
        "text": "Provided timing", "start": 0.2, "end": 1.8,
        "words": [
            {"word": "Provided", "start": 0.2, "end": 0.8},
            {"word": "timing", "start": 1.0, "end": 1.8},
        ],
    }]
    page.get_by_label("Timed lyrics JSON", exact=True).set_input_files({
        "name": "timed-lyrics.json", "mimeType": "application/json",
        "buffer": json.dumps(lyrics).encode(),
    })
    page.get_by_role("button", name="Add to queue", exact=True).click()
    page.get_by_role("button", name="Play source", exact=True).wait_for(timeout=30000)
    page.get_by_text("View synced lyrics", exact=True).click()
    assert page.get_by_role("button", name="Seek to Provided timing").is_visible()
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


@pytest.mark.parametrize("width", [320, 390, 600, 768, 1440])
def test_responsive_layout(browser_page, width):
    page, errors = browser_page
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.get_by_role("button", name="Add to queue", exact=True).is_visible()
    assert page.get_by_role("combobox", name="Theme", exact=True).is_visible()
    assert not errors


def test_titles_are_text_not_html(browser_page):
    page, errors = browser_page
    title = '<img src=x onerror="window.injected=true">'
    add_song(page, title)
    assert page.get_by_role("button", name=f"Play {title}", exact=True).is_visible()
    assert page.evaluate("window.injected === undefined")
    assert not errors


def test_pending_queue_reorders_without_jumping_the_active_song(browser_page, studio):
    page, errors = browser_page
    gate = threading.Event()
    first = "https://youtube.com/watch?v=first"
    second = "https://youtube.com/watch?v=second"
    third = "https://youtube.com/watch?v=third"

    def separate(*args, **kwargs):
        assert gate.wait(timeout=15), "The test did not release its processing gate."
        return {
            "instrumental": studio[2] / "instrumental.wav",
            "vocals": studio[2] / "vocals.wav",
        }

    with patch("yt2karaoke.separator.separate", side_effect=separate):
        try:
            for url in (first, second, third):
                page.get_by_label("YouTube URL").fill(url)
                page.get_by_role("button", name="Add to queue", exact=True).click()
                page.get_by_role("button", name="Add to queue", exact=True).wait_for(state="visible")
                playwright.expect(page.get_by_role("button", name="Add to queue", exact=True)).to_be_enabled()
            queue = page.get_by_role("list", name="Song queue", exact=True)
            playwright.expect(queue.get_by_role("listitem")).to_have_count(3)
            assert page.get_by_role("button", name=f"Move up {second}", exact=True).is_disabled()
            page.get_by_role("button", name=f"Move up {third}", exact=True).click()
            playwright.expect(queue.get_by_role("listitem").nth(1)).to_contain_text(third)
            page.get_by_role("button", name=f"Remove {second}", exact=True).click()
            playwright.expect(queue.get_by_role("listitem")).to_have_count(2)
        finally:
            gate.set()
        page.get_by_role("link", name="Download instrumental MP4", exact=True).wait_for(timeout=30000)
    assert not errors


def test_failed_conversion_can_be_retried(browser_page):
    page, errors = browser_page
    lyrics = [LyricLine("Retry works", 0.2, 1.8, [
        LyricWord("Retry", 0.2, 0.8), LyricWord("works", 1.0, 1.8),
    ])]
    with patch("yt2karaoke.transcriber.transcribe", side_effect=[RuntimeError("Test transcription failed"), lyrics]):
        page.get_by_label("YouTube URL").fill("https://youtube.com/watch?v=retry")
        page.get_by_text("Optional settings", exact=True).click()
        page.get_by_label("Song title").fill("Retry demo")
        page.get_by_role("button", name="Add to queue", exact=True).click()
        retry = page.get_by_role("button", name="Retry Retry demo", exact=True)
        retry.wait_for(timeout=30000)
        retry.click()
        page.get_by_role("button", name="Play Retry demo", exact=True).wait_for(timeout=30000)
        assert page.get_by_role("link", name="Download instrumental MP4", exact=True).is_visible()
    assert not errors


def test_skip_navigation_is_keyboard_accessible(browser_page):
    page, errors = browser_page
    page.keyboard.press("Tab")
    skip = page.get_by_role("link", name="Skip to studio", exact=True)
    playwright.expect(skip).to_be_focused()
    skip.press("Enter")
    assert page.url.endswith("#studio")
    assert not errors
