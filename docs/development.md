# Development

The application retains its Python/Flask architecture. Templates, CSS, JavaScript, fonts and the Socket.IO client are packaged together; there is no npm build step. Contribution workflow and policies are in [CONTRIBUTING.md](../CONTRIBUTING.md); coding agents should also read [AGENTS.md](../AGENTS.md).

## Install and run

Use Python 3.14 and install ffmpeg (including ffprobe) in `PATH`. Python 3.11-3.14 are supported; 3.15 is blocked by Demucs' native `sphn` dependency.

YouTube integration checks also require Node.js 22+ or Deno 2.3+ in `PATH`. Installing the project's dependencies includes the compatible EJS solver, so yt-dlp can use the installed runtime without downloading solver scripts at runtime.

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

# Opt-in full-song YouTube regression with real models and encoding
pytest tests/live -m live_youtube

# JavaScript syntax
for script in src/yt2karaoke/player/static/*.js; do node --check "$script"; done

# Wheel and source distribution using uv's isolated build backend
uv build
```

The **CI** workflow (`.github/workflows/ci.yml`) runs the JavaScript syntax checks, the deterministic suite (unit, media and browser tests) and `uv build` on every pull request and every push to `main`; it is the check pull requests must pass. The [full-song workflow](#full-song-ci) is manual only. Both share the `.github/actions/setup-environment` composite action, which installs Node, Python 3.14 with uv, FFmpeg, CPU-only dependencies and Playwright Chromium. Dependabot proposes monthly grouped updates for the pinned actions.

The browser tests run with both light and dark system preferences and use generated sine-wave media and original test lyrics. Download, separation and transcription services are mocked in these deterministic tests; the pipeline, video encoder, remix, HTTP server, queue, browser controls and file downloads are real. Theme checks cover keyboard selection, persistence, system changes, cross-tab synchronization, blocked storage, contrast and narrow layouts.

Live-audio tests measure the actual mixed 220 Hz backing and 880 Hz vocal amplitudes, including a fourfold increase from 25% to 100% vocals, unchanged backing gain, master mute and independent source levels. Microphone tests use Chromium's fake capture device, never the host microphone. They cover opt-in muted monitoring, actual pitch/EQ/compressor parameters, permission errors, stopped tracks and page cleanup. Speaker switching uses mocked sink selection; physical device routing and hardware latency still need a manual check on the target setup.

Stage-window tests verify muted playback, play/pause/seek synchronization and reload recovery. Queue journeys cover a second singer adding songs in another tab without taking over playback, names on both countdown views, configurable gaps, hold, removal of the upcoming song and zero-gap advancement.

`tests/test_browser_audio.py` runs the dependency-free Node tests in `tests/js/pitch-processor.test.cjs` as part of pytest. These feed generated PCM through the AudioWorklet processor and measure high/low pitch, unchanged duration, wet/dry gain, silence and shutdown. Node is optional for local-only conversions; this DSP check skips when it is absent. CI already installs Node for YouTube extraction.

The encoded-media tests verify H.264/AAC, 16:9 output, `yuv420p`, fast-start metadata, the absence of the test vocal frequency in the instrumental, the requested 25% gain, unchanged instrumental gain, unchanged video frames after remix, and individual highlighting of repeated words. These tests skip if ffmpeg is unavailable.

## Full-song CI

`.github/workflows/youtube-full-song.yml` runs the deterministic suite, builds and checks the installed wheel, audits dependencies, and processes the complete user-selected YouTube source with real yt-dlp, Demucs, Whisper-small and FFmpeg.

The full-song workflow is **manual only**: it does not run on pull requests or pushes and is not a required check. YouTube blocks GitHub-hosted runners ("Sign in to confirm you're not a bot"), and the job needs real models and up to 35 minutes. Maintainers run it by hand from **Actions > Full-song karaoke CI > Run workflow**, or with `gh workflow run youtube-full-song.yml --ref <branch>`, choosing the branch to test. It passes only where YouTube allows the runner's network, for example a self-hosted runner; otherwise run `pytest tests/live -m live_youtube` locally before merging changes to the YouTube, Demucs, Whisper or FFmpeg path.

The live test uses the full approximately 218-second recording, not a cropped or mocked substitute. It checks automatic word timestamps, subtitle exports, full-duration 720p H.264/AAC encoding, fast-start metadata, and a separate 10% original-vocal mix. The mixed export must preserve the video stream and timing; decoded audio must measure within 0.015 of the requested linear vocal gain. It does not claim word-for-word transcription accuracy against a reference lyric sheet.

Displayed lyric lines use their first and last word timestamps rather than Whisper's segment windows, which can otherwise hide words that extend beyond a segment boundary.

The `live_youtube` marker is excluded from normal pytest runs. Run it explicitly with `pytest tests/live -m live_youtube`. To choose where local reports and the bounded preview are saved:

```bash
YT2KARAOKE_ARTIFACT_DIR=/absolute/path/to/reports \
  pytest tests/live -m live_youtube --junitxml=/absolute/path/to/reports/live.xml
```

Pull requests from forks run with a read-only token and no repository secrets; the CI and full-song workflows need none.

The workflow uses one CPU-only Linux job, two model/encoder threads, dependency caching and public model-weight caching. It cancels an obsolete run on the same ref. Source recordings, separated song stems, full lyrics and full-song renders stay in a private temporary directory and are removed after the test. They are never cached or uploaded.

The audit exports the actual installed versions and maps only official `torch+cpu` wheels to their upstream Torch release before strict advisory lookup. This avoids silently skipping CPU wheels that are absent from PyPI. The unpublished local project is excluded; unknown third-party distributions or unsupported local version suffixes fail the audit. The pinned list is for advisory lookup only, with dependency installation and resolution disabled.

Uploaded artifacts expire after **3 days**. An explicit file allowlist contains only the technical JSON report, JUnit reports, dependency audit, and a bounded preview of at most five seconds with at most 40 lyric characters and a 10% vocal guide. Failure reports contain counts and stage/error information, not transcript text. Cancellation does not keep an obsolete run alive just to upload artifacts.

This is a live external-service test: network errors, unavailable media, YouTube sign-in/bot restrictions, model-download failures, missing tools and invalid output fail the test. It never substitutes generated media or skips a failed download. Hosted runners may be restricted by YouTube even when local access works; use an authorized runner/network if that occurs. No browser cookies or other account credentials are configured.

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
| `player/templates/stage.html` | Separate, video-only performance window |
| `player/static/studio.css` | Light/dark palettes, responsive studio and reduced-motion styles |
| `player/static/theme.js` | Pre-render theme selection, browser persistence and system changes |
| `player/static/studio.js` | Queue, player, singer countdowns, per-song mixes and errors |
| `player/static/audio-mixer.js` | Web Audio routing, device selection, live stem gain, mic EQ/compression and capture cleanup |
| `player/static/pitch-processor.js` | Streaming dual-delay AudioWorklet pitch shift and wet/dry blend |
| `player/static/stage.js` | Same-origin, muted stage synchronization and optional display placement |

## Self-hosted assets

Socket.IO client 4.8.4 is vendored from its published npm package. Outfit and Instrument Sans are from the Google Fonts repository. Their MIT and SIL OFL notices are included under `player/static/vendor/` and `player/static/fonts/` and must remain with redistributed assets.

The project's own code is MIT-licensed ([LICENSE](../LICENSE)). Because the wheel bundles these fonts, `setup.py` declares the package license as the SPDX expression `MIT AND OFL-1.1` and lists all three notices in `license_files`, so they are copied into the wheel's `.dist-info/licenses/` and the source archive.

The renderer uses FFmpeg directly so Pillow can receive current security updates. Do not restore MoviePy's `Pillow<12` constraint. Pillow 13+ and pytest 9.0.3+ are required.

## Publishing releases

`.github/workflows/publish.yml` publishes the wheel, source archive and `SHA256SUMS` to GitHub Releases when a `v*` tag is pushed. It does not publish to PyPI or produce a standalone desktop installer.

Before tagging, update **both** `version` in `setup.py` and `__version__` in `src/yt2karaoke/__init__.py` through a reviewed PR. Wait for that revision's CI to pass, then tag its merged commit. For example, when both package versions are `0.1.0`:

```bash
git tag -a v0.1.0 <merged-commit-sha> -m "Release v0.1.0"
git push origin v0.1.0
```

The tag must exactly equal `v` plus the built package's normalized Python version. For example, `0.2.0rc1` uses `v0.2.0rc1`; prerelease versions are marked as GitHub prereleases and are not marked latest. A mismatched tag or disagreement between the package and CLI versions fails before publication.

The build job uses Python 3.14 and `uv build`, installs the built wheel with CPU-only Torch dependencies, checks the installed CLI and packaged studio routes/assets, and runs the same strict dependency audit as full-song CI. Only the publishing job has `contents: write`; it downloads the verified artifacts without checking out or executing project code. Tag-specific concurrency does not cancel an in-progress publication.

Release notes include generated changes, the source commit, macOS prerequisites, first-use and upgrade commands, and the terminal-launcher limitation. The publishing job downloads the final release assets and verifies their checksums before succeeding.

For a build/install/audit dry run, manually dispatch **Publish Python packages** on the desired ref. Manual runs never publish, even when a tag is selected. Actions exposes newly added workflows for manual dispatch only after they exist on the default branch. Intermediate build artifacts expire after 3 days; published release assets do not use that retention limit.

Rerun a failed tag workflow after fixing transient infrastructure or network problems. Publishing never overwrites an existing release; if publication already created a release or draft, inspect its assets and the failed step before recovery. Changed package contents require a new version and tag, not a replacement of an existing published version. See the [release installation guide](usage.md#from-github-releases-macos) for the user-facing steps.
