"""Flask karaoke studio, queue API, and background media processing."""

from __future__ import annotations

import atexit
import os
import secrets
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_file
from flask_socketio import SocketIO, emit
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from .queue import QueuedSong, SongQueue, SongStatus
from ..pipeline import KaraokeConfig, _safe_filename, run as run_pipeline
from ..transcriber import TranscriptionError, load_lyrics
from ..video import remix_video, validate_vocals_volume


def create_app(
    output_dir: str | os.PathLike = "karaoke_output",
    whisper_model: str = "base",
    separation_model: str = "htdemucs",
    track2stem_url: Optional[str] = None,
    vocals_volume: float = 0.0,
    visual_style: str = "plasma",
) -> tuple[Flask, SocketIO]:
    """Create the studio. Original-vocal gain is selected independently per song."""
    default_volume = validate_vocals_volume(vocals_volume)
    if visual_style not in ("plasma", "gradient"):
        raise ValueError("visual_style must be plasma or gradient.")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=250 * 1024 * 1024,
    )
    socketio = SocketIO(
        app, cors_allowed_origins=os.environ.get("CORS_ALLOWED_ORIGINS") or None,
        async_mode="threading",
    )

    def report(song: QueuedSong, stage: str, progress: int) -> None:
        queue.update_progress(song.song_id, stage, progress)
        _emit_queue_update(socketio, queue)

    def clean_upload(song: QueuedSong) -> None:
        if song.audio_path is None or not song.audio_path.parent.name.startswith(".upload_"):
            return
        source_dir = song.audio_path.parent
        if not source_dir.is_relative_to(output_dir):
            return
        song.audio_path.unlink(missing_ok=True)
        if song.lyrics_path:
            song.lyrics_path.unlink(missing_ok=True)
        if source_dir.exists():
            source_dir.rmdir()

    def process_song(song: QueuedSong) -> None:
        try:
            if song.video_path is None:
                config = KaraokeConfig(
                    youtube_url=song.youtube_url, audio_path=song.audio_path,
                    lyrics_path=song.lyrics_path, title=song.title,
                    output_dir=output_dir / song.song_id, output_filename="karaoke",
                    separation_model=separation_model, vocals_volume=0.0,
                    whisper_model=whisper_model, track2stem_url=track2stem_url,
                    visual_style=song.visual_style, apply_reverb=False, apply_delay=False,
                )
                result = run_pipeline(
                    config, on_progress=lambda stage, progress: report(song, stage, progress),
                )
                song.video_path = result.video_path
                song.instrumental_path = result.instrumental_path
                song.vocals_path = result.vocals_path
                song.lyrics_json_path = result.lyrics_json_path
                song.lyrics_lrc_path = result.lyrics_lrc_path
                song.lyrics_ass_path = result.lyrics_ass_path
                song.title = result.title or song.title
                song.duration = result.duration
                song.mixes[0.0] = result.video_path
                clean_upload(song)
            if song.vocals_volume > 0:
                report(song, f"Creating {song.vocals_volume * 100:g}% vocal mix", 95)
                if song.instrumental_path is None or song.vocals_path is None:
                    raise RuntimeError("The saved stems are missing. Convert this song again.")
                mix_path = song.video_path.with_name(
                    f"karaoke_vocals_{song.vocals_volume * 100:g}pct.mp4"
                )
                remix_video(
                    song.video_path, song.instrumental_path, song.vocals_path,
                    mix_path, song.vocals_volume,
                )
                song.mixes[song.vocals_volume] = mix_path
            song.rendered_vocals_volume = song.vocals_volume
            song.status = SongStatus.READY
            song.stage = "Ready"
            song.progress = 100
            song.error = None
        except Exception as exc:
            app.logger.exception("Processing song %s failed", song.song_id)
            song.error = str(exc)
            # A failed optional mix must not discard the completed instrumental export.
            song.status = SongStatus.READY if song.video_path else SongStatus.ERROR
            song.stage = "Vocal mix failed" if song.video_path else "Conversion failed"
        finally:
            _emit_queue_update(socketio, queue)

    queue = SongQueue(worker=process_song)
    app.extensions["song_queue"] = queue
    queue.start_worker()
    atexit.register(queue.stop_worker)

    @app.errorhandler(HTTPException)
    def api_error(error: HTTPException):
        if request.path.startswith(("/api/", "/video/", "/lyrics/")):
            app.logger.warning("Request rejected (%s): %s", error.code, error.description)
            return jsonify(error=error.description, description=error.description), error.code
        return error

    def json_body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, description="Send a JSON object with the song options.")
        return data

    def options(data, *, form: bool = False) -> tuple[str, float, str]:
        title = data.get("title", "")
        if not isinstance(title, str) or len(title) > 200:
            abort(400, description="title must be text, up to 200 characters.")
        volume = data.get("vocals_volume", default_volume)
        if form:
            try:
                volume = float(volume)
            except (ValueError, TypeError):
                abort(400, description="vocals_volume must be a number between 0 and 1.")
        try:
            volume = validate_vocals_volume(volume)
        except ValueError as exc:
            abort(400, description=str(exc))
        style = data.get("visual_style", visual_style)
        if style not in ("plasma", "gradient"):
            abort(400, description="visual_style must be plasma or gradient.")
        return title.strip(), volume, style

    @app.get("/")
    def index():
        return render_template(
            "index.html", default_vocals_volume=default_volume,
            default_visual_style=visual_style,
        )

    @app.get("/api/queue")
    def get_queue():
        return jsonify(queue.get_all())

    @app.post("/api/queue")
    def add_to_queue():
        data = json_body()
        url = data.get("url")
        if not isinstance(url, str) or not url.strip():
            abort(400, description="A YouTube URL is required.")
        url = url.strip()
        try:
            parsed = urlparse(url)
            valid_url = (
                parsed.scheme in ("http", "https")
                and parsed.hostname in (
                    "youtube.com", "www.youtube.com", "m.youtube.com",
                    "music.youtube.com", "youtu.be",
                )
                and parsed.username is None and parsed.password is None
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            abort(400, description="Use a YouTube video URL, or upload a local audio file.")
        title, volume, style = options(data)
        song = queue.add(url, title, vocals_volume=volume, visual_style=style)
        _emit_queue_update(socketio, queue)
        return jsonify(song.to_dict()), 201

    @app.post("/api/queue/upload")
    def upload_to_queue():
        audio = request.files.get("audio")
        extensions = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".mp4", ".webm", ".aiff", ".aif"}
        if not audio or Path(secure_filename(audio.filename or "")).suffix.lower() not in extensions:
            abort(400, description="Choose a WAV, MP3, FLAC, M4A, OGG, AAC, MP4, WebM or AIFF file.")
        title, volume, style = options(request.form, form=True)
        source_dir = Path(tempfile.mkdtemp(dir=output_dir, prefix=".upload_"))
        audio_path = source_dir / ("source" + Path(audio.filename).suffix.lower())
        lyrics_path = None
        try:
            audio.save(audio_path)
            if audio_path.stat().st_size == 0:
                abort(400, description="The audio file is empty. Choose another file.")
            lyrics = request.files.get("lyrics")
            if lyrics and lyrics.filename:
                if Path(lyrics.filename).suffix.lower() != ".json":
                    abort(400, description="Timed lyrics must be a JSON file.")
                lyrics_path = source_dir / "lyrics.json"
                contents = lyrics.stream.read(2 * 1024 * 1024 + 1)
                if len(contents) > 2 * 1024 * 1024:
                    abort(400, description="Timed lyrics JSON must be smaller than 2 MB.")
                lyrics_path.write_bytes(contents)
                try:
                    load_lyrics(lyrics_path)
                except TranscriptionError as exc:
                    abort(400, description=str(exc))
            song = queue.add(
                "", title or Path(secure_filename(audio.filename)).stem,
                audio_path=audio_path, lyrics_path=lyrics_path,
                vocals_volume=volume, visual_style=style,
            )
        except Exception:
            audio_path.unlink(missing_ok=True)
            if lyrics_path:
                lyrics_path.unlink(missing_ok=True)
            source_dir.rmdir()
            raise
        _emit_queue_update(socketio, queue)
        return jsonify(song.to_dict()), 201

    @app.get("/api/queue/<song_id>")
    def get_song(song_id: str):
        song = queue.get_song(song_id)
        if song is None:
            abort(404, description="Song not found.")
        return jsonify(song.to_dict())

    @app.delete("/api/queue/<song_id>")
    def remove_from_queue(song_id: str):
        song = queue.get_song(song_id)
        if song is None:
            abort(404, description="Song not found.")
        if not queue.remove(song_id):
            abort(409, description="This song is processing. Wait for it to finish before removing it.")
        clean_upload(song)
        _emit_queue_update(socketio, queue)
        return jsonify(removed=song_id)

    @app.post("/api/queue/<song_id>/<direction>")
    def queue_action(song_id: str, direction: str):
        if queue.get_song(song_id) is None:
            abort(404, description="Song not found.")
        if direction in ("up", "down"):
            moved = queue.move_up(song_id) if direction == "up" else queue.move_down(song_id)
            if not moved:
                abort(409, description="This song cannot move in that direction.")
        elif direction == "retry":
            if not queue.retry(song_id):
                abort(409, description="Only failed conversions can be retried.")
        elif direction == "mix":
            _, volume, _ = options(json_body())
            if not queue.request_mix(song_id, volume):
                abort(409, description="Wait for the song to finish before creating a vocal mix.")
            song = queue.get_song(song_id)
            _emit_queue_update(socketio, queue)
            return jsonify(song.to_dict()), 200 if song.status == SongStatus.READY else 202
        else:
            abort(404, description="Queue action not found.")
        _emit_queue_update(socketio, queue)
        return jsonify(queue.get_all())

    @app.get("/video/<song_id>")
    def serve_video(song_id: str):
        song = queue.get_song(song_id)
        if song is None or song.video_path is None:
            abort(404, description="Video is not ready yet.")
        try:
            volume = validate_vocals_volume(float(request.args.get("vocals", song.rendered_vocals_volume)))
        except ValueError as exc:
            abort(400, description=str(exc))
        path = song.mixes.get(volume)
        if path is None or not path.is_file():
            abort(404, description="That vocal mix is not ready yet.")
        suffix = "instrumental" if volume == 0 else f"vocals_{volume * 100:g}pct"
        return send_file(
            path, mimetype="video/mp4", conditional=True,
            as_attachment=request.args.get("download") == "1",
            download_name=f"{_safe_filename(song.title)}_{suffix}.mp4",
        )

    @app.get("/lyrics/<song_id>")
    def serve_lyrics(song_id: str):
        song = queue.get_song(song_id)
        if song is None:
            abort(404, description="Song not found.")
        format_name = request.args.get("format", "json")
        paths = {"json": song.lyrics_json_path, "lrc": song.lyrics_lrc_path, "ass": song.lyrics_ass_path}
        if format_name not in paths:
            abort(400, description="Choose json, lrc or ass lyrics.")
        path = paths[format_name]
        if path is None or not path.is_file():
            abort(404, description="Lyrics are not ready yet.")
        return send_file(
            path, mimetype="application/json" if format_name == "json" else "text/plain",
            as_attachment=request.args.get("download") == "1",
            download_name=f"{_safe_filename(song.title)}.{'lyrics.json' if format_name == 'json' else format_name}",
        )

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @socketio.on("connect")
    def on_connect():
        emit("queue_update", queue.get_all())

    return app, socketio


def _emit_queue_update(socketio: SocketIO, queue: SongQueue) -> None:
    socketio.emit("queue_update", queue.get_all())
