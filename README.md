# yt2karaoke

Your local karaoke studio. Turn a YouTube link or local audio file into an **instrumental MP4 with word-synchronized lyrics**, then optionally export a separate mix with **0 to 100% of the original vocals**.

Demucs separates the track, Whisper finds the words, and animated visuals put the lyrics on screen. The browser studio includes a live mic mixer with pitch, EQ and compression, speaker selection, an original-vocal slider, a separate stage window, and light/dark themes. Singers can add their names and songs without interrupting playback; a configurable countdown defaults to 30 seconds between songs.

## Quick start

Requires **Python 3.11-3.14** (3.14 recommended) and **ffmpeg/ffprobe** in `PATH`. Python 3.15 is not yet supported by Demucs' `sphn` dependency.

YouTube inputs also need **Node.js 22+** or **Deno 2.3+** in `PATH`. The Python install includes yt-dlp's JavaScript challenge solver.

For published wheels, follow the [macOS release setup](docs/usage.md#from-github-releases-macos). From a source checkout:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install .
yt2karaoke player --port 5000
```

Open [localhost:5000](http://localhost:5000). Add a YouTube link or choose **Local file**, optionally enter a singer/group name, and press play when the song is ready. Adjust the original-vocal percentage live or create a separate vocal export without changing the instrumental. Use headphones before enabling mic monitoring. [Live sound, stage displays and countdown settings](docs/usage.md#live-sound-and-stage-displays) are covered in the usage guide.

For local media from the CLI:

```bash
yt2karaoke convert --audio-file ./my-song.wav -o ./output
```

Only process media and lyrics you own or are otherwise authorized to use. The software's license does not grant rights to third-party music.

## Docs

- [Usage, vocal mixes, timed lyrics, CLI and REST API](docs/usage.md)
- [Development, browser tests, media checks and packaging](docs/development.md)
- [Publishing versioned GitHub Releases](docs/development.md#publishing-releases)

Full-song CI exercises the real YouTube pipeline and a 10% vocal guide when a draft is marked ready, on `main` pushes, or manually. Reports and a bounded preview expire after 3 days; full-song media and lyrics are not uploaded.

## Stack

Python, Flask + Socket.IO, Demucs or [track2stem](https://github.com/mbianchidev/track2stem), OpenAI Whisper, FFmpeg, NumPy and Pillow. The frontend uses plain HTML, CSS, JavaScript and Web Audio/AudioWorklet, with self-hosted fonts and Socket.IO. No frontend build step or CDN access is required.

## License

[MIT](LICENSE). Bundled fonts use the SIL Open Font License; the Socket.IO client is MIT-licensed. Their license notices ship with the assets.
