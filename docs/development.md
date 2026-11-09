# Development

The application retains its Python/Flask architecture. Templates, CSS, JavaScript, fonts and the Socket.IO client are packaged together; there is no npm build step.

## Install and run

Use Python 3.14 and install ffmpeg (including ffprobe) in `PATH`. Python 3.11-3.14 are supported; 3.15 is blocked by Demucs' native `sphn` dependency.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
yt2karaoke player --port 5000
```

Headless Playwright is the browser integration. It runs in an isolated browser, not in the user's existing browser or desktop session.

## Checks

```bash
# Unit and small encoded-media checks
pytest tests --ignore=tests/e2e

# Browser journeys, including actual MP4 downloads
pytest tests/e2e

# JavaScript syntax
node --check src/yt2karaoke/player/static/studio.js

# Wheel and source distribution using uv's isolated build backend
uv build
```

The browser tests use generated sine-wave media and original test lyrics. Download, separation and transcription services are mocked in these deterministic tests; the pipeline, video encoder, remix, HTTP server, queue, browser controls and file downloads are real. Run a local-media conversion separately to exercise downloaded Demucs and Whisper models.

The encoded-media tests verify H.264/AAC, 16:9 output, `yuv420p`, fast-start metadata, the absence of the test vocal frequency in the instrumental, the requested 25% gain, unchanged instrumental gain, unchanged video frames after remix, and individual highlighting of repeated words. These tests skip if ffmpeg is unavailable.

## Modules

| Module | Responsibility |
|---|---|
| `pipeline.py` | Source selection, progress, full-strength stems, transcription and exports |
| `downloader.py` | YouTube metadata and media download |
| `separator.py` | Demucs and optional track2stem separation |
| `transcriber.py` | Whisper, validated word-timed JSON, LRC and ASS |
| `effects.py` | Optional CLI/Python vocal effects |
| `visuals.py` | Animated backgrounds, fitted lyrics and indexed word highlights |
| `video.py` | Streaming RGB frames into FFmpeg and lossless-video vocal remix |
| `player/queue.py` | Thread-safe song queue and serialized jobs |
| `player/app.py` | Flask/Socket.IO routes, upload cleanup and media serving |
| `player/templates/index.html` | Accessible studio structure |
| `player/static/studio.css` | Responsive studio and reduced-motion styles |
| `player/static/studio.js` | Queue, player, per-song mix controls and errors |

## Self-hosted assets

Socket.IO client 4.8.4 is vendored from its published npm package. Outfit and Instrument Sans are from the Google Fonts repository. Their MIT and SIL OFL notices are included under `player/static/vendor/` and `player/static/fonts/` and must remain with redistributed assets.

The renderer uses FFmpeg directly so Pillow can receive current security updates. Do not restore MoviePy's `Pillow<12` constraint. Pillow 13+ and pytest 9.0.3+ are required.
