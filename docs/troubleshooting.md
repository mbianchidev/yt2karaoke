# Troubleshooting

Start with the terminal running `yt2karaoke`; conversion errors are printed
there and shown in the studio queue. When reporting a problem, use the
[bug report form](https://github.com/mbianchidev/yt2karaoke/issues/new?template=bug_report.yml)
and redact anything private.

## Installation

**Dependency installation fails on Python 3.15.** Demucs' native `sphn`
dependency does not support 3.15 yet. Create the environment with Python 3.11
to 3.14; 3.14 is recommended.

**`ffmpeg was not found` or `ffprobe was not found`.** Install ffmpeg, which
includes ffprobe, and make sure both are in `PATH` (for example
`brew install ffmpeg` on macOS or `sudo apt-get install ffmpeg` on
Debian/Ubuntu). Open a new terminal after installing.

## YouTube sources

**Downloads fail with challenge, signature, or missing-format errors.** Install
Node.js 22+ or Deno 2.3+ and make sure `node --version` or `deno --version`
works in the same terminal. yt2karaoke enables both runtimes and the
`yt-dlp[default]` dependency includes the matching challenge solver; see the
[yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

**YouTube asks to sign in or reports bot detection.** Some networks, VPNs, and
hosted CI runners are restricted by YouTube even when the same link works
elsewhere. Try another network, or convert a local file you are authorized to
use. yt2karaoke does not read browser cookies or account credentials.

**A link is rejected.** The studio accepts YouTube video URLs. Upload other
media with **Local file**.

## Studio

**`Address already in use` or port 5000 is busy.** Start the studio on another
port, for example `yt2karaoke player --port 5001`. On macOS, AirPlay Receiver
can occupy port 5000.

**The first conversion is slow.** Demucs and Whisper download their models on
first use, which needs internet access. Later conversions reuse the cached
models. Separation and transcription run on your CPU or GPU and can take
several minutes for a full song.

**An upload is rejected as too large.** Each request is limited to 250 MB.
Trim or compress the source first.

**The microphone is unavailable.** Open the studio on `localhost` or HTTPS,
select **Enable microphone**, and allow access when the browser asks. If you
denied access earlier, re-enable it in the browser's site settings. Microphone
audio never leaves the browser.

**Speakers cannot be selected.** Speaker selection depends on browser support.
Chromium-based browsers support it; other browsers use the system output and
say so beside the speaker controls.

**The stage window does not open.** Allow pop-ups for the studio's address and
select **Open stage window** again.

## Output quality

**Lyrics are wrong or out of sync.** Automatic transcription is not perfect,
especially with dense backing tracks. Try a larger `--whisper-model` (slower)
or set `--language`. For full control, download the timed lyrics JSON, edit
it, and convert the local media again with it
([format](usage.md#timed-lyrics-format)).

**Original vocals bleed into the instrumental.** AI separation can leave some
vocal bleed. Review the result with headphones. Try another Demucs model with
`--separation-model`, or a running
[track2stem](usage.md#track2stem) service.
