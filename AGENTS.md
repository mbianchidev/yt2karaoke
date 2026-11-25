# Working on yt2karaoke

Read [README.md](README.md), [CONTRIBUTING.md](CONTRIBUTING.md), and the
[development guide](docs/development.md) before editing.

## Repository map

- `src/yt2karaoke/`: pipeline, downloader, separator, transcriber, effects,
  visuals, video encoding, and the CLI. See the
  [module table](docs/development.md#modules).
- `src/yt2karaoke/player/`: Flask/Socket.IO studio, queue, templates, and
  static assets. There is no frontend build step.
- `tests/`: deterministic unit, media, and Playwright tests; `tests/live/` is
  the opt-in full-song YouTube test; `tests/js/` holds Node DSP tests.
- `scripts/ci_audit_requirements.py`: dependency audit helper used by CI.
- `.github/workflows/`: `ci.yml` (every PR), `youtube-full-song.yml`
  (ready-for-review, `main`, manual), `publish.yml` (GitHub Releases).
- `docs/`: [user and developer documentation](docs/README.md).

## Setup and checks

Use Python 3.14 (3.11 to 3.14 supported), ffmpeg/ffprobe in `PATH`, and
Node.js 22+ or Deno 2.3+.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium

for script in src/yt2karaoke/player/static/*.js; do node --check "$script"; done
python -m pytest tests -m "not live_youtube"
uv build
```

Run `pytest tests/live -m live_youtube` only when the change affects the real
YouTube, Demucs, Whisper, or FFmpeg path; it downloads models and media.
Do not create tags or publish releases to validate a change; see
[publishing releases](docs/development.md#publishing-releases).

## Invariants

- Keep separated vocals at full strength for transcription and saved stems.
  Apply `vocals_volume` once, at final audio mixing.
- Derive lyric line bounds from Whisper word timestamps when present; segment
  windows can hide sung words.
- Keep `yt-dlp[default]` and enable Node/Deno runtimes for both metadata and
  downloads so yt-dlp has its matching EJS challenge solver.
- Bump `version` in `setup.py` and `__version__` in
  `src/yt2karaoke/__init__.py` together.
- Keep the vendored Socket.IO client and fonts self-hosted with their license
  files. Do not add CDN dependencies or restore MoviePy's `Pillow<12` pin.
- The studio is a local server bound to `127.0.0.1` by default. Do not change
  that default or weaken upload and path validation.
- Tests use generated media and original lyrics only. Mock download,
  separation, and transcription in deterministic tests. Never commit
  copyrighted recordings, cookies, credentials, or personal data.
- Live CI must never cache or upload full-song media, stems, or lyrics.
- Follow [ACCESSIBILITY.md](ACCESSIBILITY.md) for UI changes and update the
  relevant docs when behavior, options, or setup change.
