# Using the karaoke studio

## Setup

Python 3.11-3.14 are supported; 3.14 is recommended. Demucs' native `sphn` dependency does not yet support 3.15. Install ffmpeg (including ffprobe) in `PATH`.

For YouTube sources, install Node.js 22+ or Deno 2.3+ in `PATH` as well. The downloader enables either runtime automatically, and the project's `yt-dlp[default]` dependency includes its matching `yt-dlp-ejs` challenge solver. No browser cookies or remote solver downloads are configured. See the [yt-dlp EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS) for runtime installation details.

### From GitHub Releases (macOS)

Download the `.whl` file from a published [GitHub Release](https://github.com/mbianchidev/yt2karaoke/releases). Run the following in the download directory, replacing `0.1.0` with the downloaded version:

```bash
brew install uv ffmpeg node
uvx --python 3.14 --from ./yt2karaoke-0.1.0-py3-none-any.whl \
  yt2karaoke player --port 5000
```

`uvx` downloads Python if needed and installs the wheel's Python dependencies in a managed environment. No source checkout or manually activated virtual environment is needed. The wheel does not bundle ffmpeg, Node.js or AI model weights.

Each release also includes a source archive and `SHA256SUMS`. To check downloaded packages, download both archives and the checksum file into the same directory, then run `shasum -a 256 -c SHA256SUMS`.

To upgrade, stop the running server with Ctrl+C, download the new wheel and rerun the command with its filename. Existing karaoke output files are retained.

This is still a terminal-launched local web app, not a standalone desktop installer. Packages are published to GitHub Releases, not PyPI; do not omit `--from` or substitute an unverified package-index download.

### From a source checkout

Create a Python environment and install the project from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install .
yt2karaoke player --port 5000 --output-dir ./karaoke_output
```

Open [localhost:5000](http://localhost:5000). Models download on first use, so the initial conversion needs internet access and may take longer. Later local-file conversions can use cached models. The browser loads its fonts and Socket.IO client from the studio itself.

For either setup, run the launcher from the directory where you want `karaoke_output` created, or set `--output-dir` to an explicit path.

The player is a local development server. Keep the default loopback host; do not expose it publicly. The queue is held in memory for the running session. Exported videos, stems and lyrics remain in the output directory after shutdown.

If something does not work, see [Troubleshooting](troubleshooting.md).

### Stored data and uninstalling

- **Outputs** stay in the output directory (`karaoke_output` for the player, the current directory for `convert`) until you delete them. Temporary `.yt2karaoke_work_*` folders are removed after each conversion. Uploaded source files are removed after a successful conversion or when you remove the song from the queue; a failed upload is kept so you can retry it.
- **Models** are cached by their libraries, typically Demucs weights in `~/.cache/torch/hub/checkpoints` and Whisper weights in `~/.cache/whisper`. Other tools that use those libraries may share these caches; delete them only if nothing else needs them.
- **Browser**: the studio saves only its theme preference in the browser's local storage for the studio address.
- **Program**: for a source checkout, deactivate and delete its `.venv` folder. For a release wheel run with `uvx`, `uv cache clean yt2karaoke` removes uv's cached copy.

## Studio appearance

Use **Theme** in the header to choose **System**, **Light**, or **Dark**. System is the default and follows your operating system's appearance, including changes while the studio is open. An explicit Light or Dark choice overrides the system setting.

Your preference is saved locally in the browser, survives reloads, and stays in sync across studio tabs on the same origin. If browser storage is blocked, theme changes still work for the current page and a save failure is shown. The studio theme does not change video backgrounds or exported media.

## Live sound and stage displays

Use a current browser on **localhost or HTTPS** for microphone access. Chromium-based browsers support the full device controls; browsers without speaker-selection APIs use the system sound output and say so beside the speaker controls.

In **Live sound**, choose a microphone and select **Enable microphone**. Capture starts only on your request, and monitoring starts **muted**. Use headphones before turning on **Hear my microphone** to avoid speaker feedback. **Disable microphone** releases the device; leaving or reloading the studio also releases it. Microphone audio stays in the browser and is not recorded, uploaded, or included in downloads.

**Natural**, **High pitch** (+7 semitones) and **Low pitch** (-7 semitones) change the live microphone. **Voice pitch** allows -12 to +12 semitones without changing song speed; **Pitch effect mix** blends the shifted and natural voice. Bass, mid and treble provide +/-12 dB at 150 Hz, 1 kHz and 4 kHz. **Compression** evens out loud and quiet notes; 0% bypasses compression. Effects apply only to the live mic, not the original singer or exported files.

**Speaker volume** and the player's **Playback volume** are linked master controls for the song, original vocals and monitored microphone. The speaker icon mutes the entire output. **Backing track volume**, **Microphone volume** and **Original vocals** adjust those sources independently. A master compressor reduces clipping when sources are combined.

Choose **Speakers** to route the whole mix to an available output. Device names usually become available after microphone permission; use **Refresh devices** after connecting hardware. Where available, **Choose speakers** opens the browser's output chooser. A rejected output change leaves the previous output selected. Device selection cannot eliminate Bluetooth or hardware monitoring latency.

**Open stage window** shows a synchronized, muted video in a separate window. Move it to your preferred display and use its **Full screen** button, keeping the mixer and queue in the studio. Play, pause, seeks, song changes and singer countdowns follow the main player. Audio plays only through the studio, not twice. **Find displays**, where supported, requests window-management permission and lets you choose a display; otherwise move the window manually. Allow pop-ups if the browser blocks it.

## Add and play a song

Choose **YouTube link** or **Local file**, then **Add to queue**. Local inputs can be WAV, MP3, FLAC, M4A, OGG, AAC, MP4, WebM or AIFF; the request limit is 250 MB.

**Optional settings** lets you set a title. For local files it also accepts word-timed lyrics JSON instead of automatic transcription. Use audio and lyrics you own or are otherwise authorized to process.

**Singer / group name** is optional, accepts up to 100 characters, and appears beside the song in the queue and in the stage countdown. You can keep adding songs while another song plays. Adding a song from another tab connected to the same studio does not take over playback or start the guest tab's player.

The queue processes one song at a time and reports its current stage. The first song is selected automatically; playback starts when you press play. You can seek, adjust playback volume, open full screen, reorder pending songs, retry failed conversions, and remove songs that are not processing.

When a song ends, the studio announces the next ready song and singer with a **30-second countdown** in both the preview and stage window. Set **Seconds between songs** above the queue to any non-negative whole number; **0** starts the next ready song immediately. This setting applies to the current studio page. Changing it during a countdown restarts that countdown with the new duration.

**Start now** skips the remaining countdown. **Hold the stage** cancels automatic advancement until you press play or choose another song. If the next song is still processing, the stage waits; the countdown begins when a song becomes ready. Removing a song during its countdown prevents it from playing and selects the next ready song, or waits for another one.

**View synced lyrics** shows the timestamps and lets you jump to a lyric line. **Download timed lyrics** saves editable JSON; LRC and ASS exports are also available through the API and output directory.

Automatic transcription is not a guarantee of perfect lyrics, especially with screamed vocals or dense backing tracks. Review the preview and timestamps. If needed, edit the exported JSON and submit it with the original local media.

## Instrumental and original-vocal exports

At **0%**, the output contains only the separated instrumental. Transcription always uses the full-strength isolated vocals, even when the output is instrumental-only.

AI separation can leave some vocal bleed. Review the instrumental with headphones before using it for a performance.

Turn on **Add original vocals** and use a preset or slider to hear the chosen percentage immediately. Live playback combines the instrumental video's audio with the saved, full-strength vocal stem. Changing the slider does not render a video or interrupt the playing song, and creating an export does not replace the live player's instrumental base.

Select **Create vocal mix** for the selected ready song to save that vocal percentage as a separate MP4. **Download instrumental MP4** remains available independently of **Download 25% vocal mix** (or your chosen percentage). Mic monitoring, pitch, EQ, compression and live volume settings do not change these exports.

A vocal mix reuses the saved full-strength stems and copies the existing H.264 video stream. It does not repeat separation, transcription or video rendering, so the baked-in lyric timing is unchanged. The percentage is a linear gain on the original isolated vocals; the instrumental level is retained and a peak limiter prevents clipping.

Settings chosen before adding a song are saved for that song. Video background changes apply only to new songs. A failed optional mix keeps the instrumental available and displays the error.

## Timed lyrics format

A `.json` file contains a non-empty array of lyric lines. Times are in seconds, finite and non-negative. Lines must be ordered and non-overlapping; words must be ordered, inside their line, and match its text. The pipeline also checks that supplied lyrics do not end after the audio.

This example contains original test text:

```json
[
  {
    "text": "Step into the light",
    "start": 1.0,
    "end": 3.0,
    "words": [
      {"word": "Step", "start": 1.0, "end": 1.3},
      {"word": "into", "start": 1.4, "end": 1.8},
      {"word": "the", "start": 1.9, "end": 2.2},
      {"word": "light", "start": 2.3, "end": 3.0}
    ]
  }
]
```

## CLI

```bash
# Instrumental karaoke from authorized local media
yt2karaoke convert --audio-file ./my-song.wav -o ./output

# Use your reviewed word timestamps
yt2karaoke convert --audio-file ./my-song.wav --lyrics-file ./my-song.lyrics.json -o ./output

# Include 25% original vocals without added voice effects
yt2karaoke convert --audio-file ./my-song.wav --vocals-volume 0.25 \
  --no-reverb --no-delay --filename my-song-guide -o ./output

# Process a YouTube source you are authorized to use
yt2karaoke convert "https://youtube.com/watch?v=YOUR_VIDEO_ID" -o ./output
```

Conversion options:

| Option | Default | Purpose |
|---|---|---|
| `-o, --output-dir` | `.` | Output directory |
| `--audio-file` | None | Local media instead of the URL argument |
| `--lyrics-file` | None | Word-timed JSON instead of Whisper |
| `--filename` | Detected title | Output filename stem |
| `--vocals-volume` | `0.0` | Original vocal gain from 0 to 1 |
| `--whisper-model` | `base` | `tiny`, `base`, `small`, `medium` or `large` |
| `--language` | Auto-detect | Transcription language code |
| `--separation-model` | `htdemucs` | Demucs model |
| `--track2stem-url` | None | Optional remote separation service |
| `--visual-style` | `plasma` | `plasma` or `gradient` |
| `--visual-speed` | `0.5` | Background animation speed |
| `--width`, `--height` | `1280`, `720` | Positive even video dimensions |
| `--fps` | `24` | Video frame rate |
| `--reverb / --no-reverb` | On | Reverb on non-muted vocals |
| `--delay / --no-delay` | On | Delay on non-muted vocals |
| `--distortion / --no-distortion` | Off | Vocal distortion |
| `--chorus / --no-chorus` | Off | Vocal chorus |

The CLI effect flags apply only to CLI/Python conversions that include vocals. The browser's live effects apply to your microphone; its original-vocal guide and exported vocal mixes use the unprocessed saved stem.

Player options include `--host` (default `127.0.0.1`), `--port` (5000), `--output-dir` (`karaoke_output`), `--whisper-model`, `--separation-model`, `--track2stem-url`, `--vocals-volume`, `--visual-style` and `--debug`. `--vocals-volume` and `--visual-style` set the studio's initial mix and background choices.

Outputs include `.mp4`, `_instrumental.wav`, full-strength `_vocals.wav`, `.lrc`, `.ass` and `.lyrics.json`.

## track2stem

The default separator runs Demucs locally. To use a running [track2stem](https://github.com/mbianchidev/track2stem) service instead:

```bash
yt2karaoke player --track2stem-url http://localhost:8080
yt2karaoke convert --audio-file ./my-song.wav --track2stem-url http://localhost:8080 -o ./output
```

The Python client is also available:

```python
from yt2karaoke.separator import Track2StemClient

client = Track2StemClient("http://localhost:8080")
stems = client.separate("my-song.wav", "./stems", vocals_volume=1.0)
```

## Python API

```python
from yt2karaoke.pipeline import KaraokeConfig, run

result = run(
    KaraokeConfig(
        audio_path="my-song.wav",
        output_dir="./output",
        vocals_volume=0.0,
        whisper_model="small",
        visual_style="gradient",
    ),
    on_progress=lambda stage, progress: print(stage, progress),
)
print(result.video_path)
print(result.lyrics_json_path)
```

Provide exactly one of `youtube_url` or `audio_path`. Optional `lyrics_path` accepts the JSON format above. Isolated vocals remain at full strength in the output, regardless of final mix gain.

## REST API

Errors return JSON with `error` and `description` fields and a non-success HTTP status.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/queue` | Queue snapshot |
| `POST` | `/api/queue` | Add `{"url": "...", "title": "...", "performer": "Test duo", "vocals_volume": 0.25, "visual_style": "gradient"}` |
| `POST` | `/api/queue/upload` | Multipart `audio`, optional `lyrics`, `title`, `performer`, `vocals_volume`, `visual_style` |
| `GET` | `/api/queue/<id>` | Song status, progress and export URLs |
| `DELETE` | `/api/queue/<id>` | Remove a song that is not processing |
| `POST` | `/api/queue/<id>/up` or `/down` | Reorder a pending song |
| `POST` | `/api/queue/<id>/retry` | Retry a failed conversion |
| `POST` | `/api/queue/<id>/mix` | Select or create a mix with `{"vocals_volume": 0.25}` |
| `GET` | `/video/<id>?vocals=0` | Stream the instrumental MP4, with byte-range support |
| `GET` | `/video/<id>?vocals=0.25&download=1` | Download an already-created 25% mix |
| `GET` | `/audio/<id>/<stem>` | Stream the unchanged `vocals` or `instrumental` WAV with byte-range support |
| `GET` | `/stage` | Stage-window view controlled by its originating studio tab |
| `GET` | `/lyrics/<id>?format=json` | Word-timed lyrics; also supports `lrc`, `ass` and `download=1` |

The mix endpoint returns `202` when processing is queued and `200` when selecting an existing export. Per-song `video_url` selects the last successfully rendered mix; `instrumental_url` always downloads the instrumental. `playback_url` always streams the instrumental video, and `vocals_audio_url` supplies its full-strength vocal stem for live mixing. `performer` is trimmed text, limited to 100 characters. The browser uses Socket.IO `queue_update` events and a polling fallback; microphone, output-device and countdown settings stay local to the operator's page.
