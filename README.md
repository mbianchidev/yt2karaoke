# yt2karaoke

Your local karaoke studio. Turn a YouTube link or local audio file into an **instrumental MP4 with word-synchronized lyrics**, then optionally export a separate mix with **0 to 100% of the original vocals**.

Demucs separates the track, Whisper finds the words, and animated visuals put the lyrics on screen. The browser studio includes a song queue, processing updates, playback controls, downloads, and a per-song vocal guide.

## Quick start

Requires **Python 3.11-3.14** (3.14 recommended) and **ffmpeg/ffprobe** in `PATH`. Python 3.15 is not yet supported by Demucs' `sphn` dependency.

YouTube inputs also need **Node.js 22+** or **Deno 2.3+** in `PATH`. The Python install includes yt-dlp's JavaScript challenge solver.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install .
yt2karaoke player --port 5000
```

Open [localhost:5000](http://localhost:5000). Add a YouTube link or choose **Local file**. Instrumental-only is the default. Select a ready song, choose a vocal percentage, and create a separate vocal mix without changing the instrumental export.

For local media from the CLI:

```bash
yt2karaoke convert --audio-file ./my-song.wav -o ./output
```

Only process media and lyrics you own or are otherwise authorized to use. The software's license does not grant rights to third-party music.

## Docs

- [Usage, vocal mixes, timed lyrics, CLI and REST API](docs/usage.md)
- [Development, browser tests, media checks and packaging](docs/development.md)

Full-song CI exercises the real YouTube pipeline and a 10% vocal guide when a draft is marked ready, on `main` pushes, or manually. Reports and a bounded preview expire after 3 days; full-song media and lyrics are not uploaded.

## Stack

Python, Flask + Socket.IO, Demucs or [track2stem](https://github.com/mbianchidev/track2stem), OpenAI Whisper, FFmpeg, NumPy and Pillow. The frontend is plain HTML, CSS and JavaScript with self-hosted fonts and Socket.IO. No frontend build step or CDN access is required.

## License

[MIT](LICENSE). Bundled fonts use the SIL Open Font License; the Socket.IO client is MIT-licensed. Their license notices ship with the assets.
