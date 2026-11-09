# Using the karaoke studio

## Setup

Install ffmpeg (including ffprobe) with your operating system's package manager, create a Python environment, and install the project. Python 3.14 is the newest supported version; Demucs' native `sphn` dependency does not yet support 3.15.

For YouTube sources, install Node.js 22+ or Deno 2.3+ in `PATH` as well. The downloader enables either runtime automatically, and the project's `yt-dlp[default]` dependency includes its matching `yt-dlp-ejs` challenge solver. No browser cookies or remote solver downloads are configured. See the [yt-dlp EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS) for runtime installation details.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install .
yt2karaoke player --port 5000 --output-dir ./karaoke_output
```

Open [localhost:5000](http://localhost:5000). Models download on first use, so the initial conversion needs internet access and may take longer. Later local-file conversions can use cached models. The browser loads its fonts and Socket.IO client from the studio itself.

The player is a local development server. Keep the default loopback host; do not expose it publicly. The queue is held in memory for the running session. Exported videos, stems and lyrics remain in the output directory after shutdown.

## Add and play a song

Choose **YouTube link** or **Local file**, then **Add to queue**. Local inputs can be WAV, MP3, FLAC, M4A, OGG, AAC, MP4, WebM or AIFF; the request limit is 250 MB.

**Optional settings** lets you set a title. For local files it also accepts word-timed lyrics JSON instead of automatic transcription. Use audio and lyrics you own or are otherwise authorized to process.

The queue processes one song at a time and reports its current stage. The first song is selected automatically; playback starts when you press play. A finished song advances to the next ready song. You can seek, adjust playback volume, open full screen, reorder pending songs, retry failed conversions, and remove songs that are not processing.

**View synced lyrics** shows the timestamps and lets you jump to a lyric line. **Download timed lyrics** saves editable JSON; LRC and ASS exports are also available through the API and output directory.

Automatic transcription is not a guarantee of perfect lyrics, especially with screamed vocals or dense backing tracks. Review the preview and timestamps. If needed, edit the exported JSON and submit it with the original local media.

## Instrumental and original-vocal exports

At **0%**, the output contains only the separated instrumental. Transcription always uses the full-strength isolated vocals, even when the output is instrumental-only.

AI separation can leave some vocal bleed. Review the instrumental with headphones before using it for a performance.

Turn on **Add original vocals**, use a preset or choose a percentage, and select **Create vocal mix** for the selected ready song. **Download instrumental MP4** remains available independently of **Download 25% vocal mix** (or your chosen percentage).

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

Voice effects apply only to CLI/Python conversions that include vocals. The browser studio mixes the unprocessed original vocal stem.

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
| `POST` | `/api/queue` | Add `{"url": "...", "title": "...", "vocals_volume": 0.25, "visual_style": "gradient"}` |
| `POST` | `/api/queue/upload` | Multipart `audio`, optional `lyrics`, `title`, `vocals_volume`, `visual_style` |
| `GET` | `/api/queue/<id>` | Song status, progress and export URLs |
| `DELETE` | `/api/queue/<id>` | Remove a song that is not processing |
| `POST` | `/api/queue/<id>/up` or `/down` | Reorder a pending song |
| `POST` | `/api/queue/<id>/retry` | Retry a failed conversion |
| `POST` | `/api/queue/<id>/mix` | Select or create a mix with `{"vocals_volume": 0.25}` |
| `GET` | `/video/<id>?vocals=0` | Stream the instrumental MP4, with byte-range support |
| `GET` | `/video/<id>?vocals=0.25&download=1` | Download an already-created 25% mix |
| `GET` | `/lyrics/<id>?format=json` | Word-timed lyrics; also supports `lrc`, `ass` and `download=1` |

The mix endpoint returns `202` when processing is queued and `200` when selecting an existing export. Per-song `video_url` selects the last successfully rendered mix; `instrumental_url` always downloads the instrumental. The browser uses Socket.IO `queue_update` events and a polling fallback.
