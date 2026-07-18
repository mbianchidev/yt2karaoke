# yt2karaoke

**yt2karaoke** turns YouTube links into karaoke experiences.

Give it a YouTube URL and it will:

1. **Download** the audio track via [yt-dlp](https://github.com/yt-dlp/yt-dlp).
2. **Separate** the audio into **vocals + instrumental** using [Demucs](https://github.com/facebookresearch/demucs) — the same AI model that powers [@mbianchidev/track2stem](https://github.com/mbianchidev/track2stem).
3. **Transcribe** the lyrics with word-level timestamps using [OpenAI Whisper](https://github.com/openai/whisper).
4. **Apply** optional voice effects (reverb, delay, distortion, chorus) to the vocals.
5. **Generate** trippy, colorful, slow-moving animated background visuals (plasma waves / color gradients).
6. **Render** a karaoke video: instrumental audio + word-by-word highlighted lyrics overlaid on the animated background.
7. **Serve** a browser-based **player** with a **song queue** so you can line up songs and enjoy the show.

---

## Features

| Feature | Details |
|---|---|
| YouTube download | Any public video via yt-dlp |
| Stem separation | Vocals + instrumental (Demucs / track2stem API) |
| Vocals volume control | Blend original vocals into the mix (0 = muted, 1 = full) |
| Lyrics extraction | OpenAI Whisper — `tiny` → `large` model sizes |
| Karaoke sync | Word-level timestamp highlighting |
| Subtitle export | LRC (media players) + ASS (advanced karaoke tags) |
| Voice effects | Reverb, delay/echo, distortion, chorus via `pedalboard` |
| Animated visuals | Plasma waves or color gradient (NumPy/Pillow, no GPU needed) |
| Video output | MP4 (H.264 + AAC) via MoviePy |
| Web player | Flask + SocketIO, live queue updates via WebSocket |
| Song queue | Add, remove, reorder songs; auto-plays when ready |
| CLI | `yt2karaoke convert` + `yt2karaoke player` commands |

---

## Quick Start

### Requirements

- Python ≥ 3.9
- `ffmpeg` (must be in `PATH` — used by yt-dlp and MoviePy)

### Install

```bash
pip install -r requirements.txt
pip install -e .
```

### Convert a single song (CLI)

```bash
yt2karaoke convert "https://youtube.com/watch?v=dQw4w9WgXcQ" -o ./output
```

The output directory will contain:
- `<title>.mp4` — karaoke video
- `<title>_instrumental.wav` — backing track
- `<title>_vocals.wav` — isolated vocals
- `<title>.lrc` — LRC lyrics file
- `<title>.ass` — ASS subtitle file (karaoke tags)

### Start the web player

```bash
yt2karaoke player --port 5000 --output-dir ./karaoke_output
```

Open [http://localhost:5000](http://localhost:5000) in your browser, paste a YouTube URL and enjoy!

---

## CLI Reference

### `yt2karaoke convert`

```
Usage: yt2karaoke convert [OPTIONS] URL

  Convert a YouTube URL to a karaoke video.

Options:
  -o, --output-dir TEXT         Output directory.  [default: .]
  --filename TEXT               Output filename stem (no extension).
  --vocals-volume FLOAT         Volume of original vocals in the mix
                                (0=muted, 1=full).  [default: 0.0]
  --whisper-model [tiny|base|small|medium|large]
                                Whisper model size.  [default: base]
  --separation-model TEXT       Demucs model.  [default: htdemucs]
  --track2stem-url TEXT         URL of a running track2stem service.
  --visual-style [plasma|gradient]
                                Background visual style.  [default: plasma]
  --visual-speed FLOAT          Animation speed (lower = slower).  [default: 0.5]
  --width INTEGER               Video width.  [default: 1280]
  --height INTEGER              Video height.  [default: 720]
  --fps FLOAT                   Frame rate.  [default: 24.0]
  --language TEXT               Language code (auto-detect if omitted).
  --reverb / --no-reverb        Apply reverb to vocals.  [default: reverb]
  --delay / --no-delay          Apply delay/echo to vocals.  [default: delay]
  --distortion / --no-distortion  Apply distortion.  [default: no-distortion]
  --version                     Show version and exit.
  --help                        Show this message and exit.
```

### `yt2karaoke player`

```
Usage: yt2karaoke player [OPTIONS]

  Start the yt2karaoke web player.

Options:
  --host TEXT                   Bind host.  [default: 127.0.0.1]
  --port INTEGER                Port.  [default: 5000]
  -o, --output-dir TEXT         Directory for karaoke files.  [default: karaoke_output]
  --whisper-model [tiny|base|small|medium|large]
                                Whisper model for transcription.  [default: base]
  --separation-model TEXT       Demucs model.  [default: htdemucs]
  --track2stem-url TEXT         URL of a running track2stem service.
  --vocals-volume FLOAT         Volume of original vocals.  [default: 0.0]
  --visual-style [plasma|gradient]
  --debug                       Enable Flask debug mode.
  --help                        Show this message and exit.
```

---

## Using track2stem as the separation backend

yt2karaoke uses [Demucs](https://github.com/facebookresearch/demucs) directly by default. If you prefer to offload the heavy AI processing to a running [@mbianchidev/track2stem](https://github.com/mbianchidev/track2stem) Docker service, pass its URL:

```bash
# Start track2stem (see its README)
docker-compose -f path/to/track2stem/docker-compose.yml up -d

# Use it as the separation backend
yt2karaoke convert "https://youtube.com/watch?v=..." --track2stem-url http://localhost:8080
```

You can also use the Python API directly:

```python
from yt2karaoke.separator import Track2StemClient

client = Track2StemClient("http://localhost:8080")
if client.health_check():
    stems = client.separate("audio.wav", output_dir="./stems", vocals_volume=0.3)
    print(stems["vocals"], stems["instrumental"])
```

---

## Python API

```python
from yt2karaoke.pipeline import KaraokeConfig, run

result = run(KaraokeConfig(
    youtube_url="https://youtube.com/watch?v=dQw4w9WgXcQ",
    output_dir="./output",
    vocals_volume=0.2,         # blend in 20% of original vocals
    whisper_model="small",
    visual_style="plasma",
    apply_reverb=True,
    apply_delay=True,
))

print(result.video_path)        # Path to the MP4 file
print(result.lyrics_lrc_path)   # LRC subtitle file
```

### Individual modules

```python
# Download
from yt2karaoke.downloader import download_audio, get_video_info

# Separate vocals + instrumental
from yt2karaoke.separator import separate

# Transcribe with timestamps
from yt2karaoke.transcriber import transcribe, lines_to_lrc, lines_to_ass

# Apply voice effects
from yt2karaoke.effects import apply_effects, apply_effects_numpy

# Generate animated frames
from yt2karaoke.visuals import generate_frames, render_lyric_frame

# Build video
from yt2karaoke.video import build_video

# Web player + queue
from yt2karaoke.player.app import create_app
from yt2karaoke.player.queue import SongQueue
```

---

## Player REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web player UI |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/queue` | List all queued songs |
| `POST` | `/api/queue` | Add a song `{"url": "...", "title": "..."}` |
| `GET` | `/api/queue/<id>` | Get song status |
| `DELETE` | `/api/queue/<id>` | Remove a queued song |
| `POST` | `/api/queue/<id>/up` | Move song up in queue |
| `POST` | `/api/queue/<id>/down` | Move song down in queue |
| `GET` | `/video/<id>` | Stream the karaoke video |

Real-time queue updates are delivered via **WebSocket** (Socket.IO event `queue_update`).

---

## Architecture

```
src/
└── yt2karaoke/
    ├── cli.py              CLI entry point (click)
    ├── pipeline.py         Orchestrates the full processing pipeline
    ├── downloader.py       YouTube audio download (yt-dlp)
    ├── separator.py        Vocal/instrumental separation (Demucs + track2stem client)
    ├── transcriber.py      Lyrics extraction + timestamp sync (Whisper)
    ├── effects.py          Voice effects: reverb, delay, distortion (pedalboard / NumPy)
    ├── visuals.py          Animated background frame generator (NumPy + Pillow)
    ├── video.py            Karaoke video assembler (MoviePy)
    └── player/
        ├── app.py          Flask web player + SocketIO
        ├── queue.py        Thread-safe song queue with background worker
        └── templates/
            └── index.html  Browser player UI
```

---

## Development

```bash
# Install the project and test dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Check CLI help
yt2karaoke --help
```

---

## License

MIT
