"""Flask web player for yt2karaoke.

Provides:
- A browser-based video player for karaoke videos.
- A REST/SocketIO API for the song queue.
- Background processing of YouTube URLs into karaoke videos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, send_file, abort
from flask_socketio import SocketIO, emit

from .queue import SongQueue, SongStatus, QueuedSong
from ..pipeline import KaraokeConfig, run as run_pipeline
from ..downloader import get_video_info, DownloadError


def create_app(
    output_dir: str | os.PathLike = "karaoke_output",
    whisper_model: str = "base",
    separation_model: str = "htdemucs",
    track2stem_url: Optional[str] = None,
    vocals_volume: float = 0.0,
    visual_style: str = "plasma",
) -> tuple[Flask, SocketIO]:
    """Create and configure the Flask application.

    Args:
        output_dir: Directory where processed karaoke files are stored.
        whisper_model: Whisper model size for transcription.
        separation_model: Demucs model for stem separation.
        track2stem_url: Optional URL of a track2stem service.
        vocals_volume: Volume level for original vocals in the mix.
        visual_style: Background visual style.

    Returns:
        A ``(Flask app, SocketIO)`` tuple.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "yt2karaoke-secret")

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    # ------------------------------------------------------------------
    # Song queue + background worker
    # ------------------------------------------------------------------

    def process_song(song: QueuedSong) -> None:
        """Process a queued song — download, separate, transcribe, render."""
        # Fetch title if not set
        if not song.title:
            try:
                info = get_video_info(song.youtube_url)
                song.title = info.get("title", song.youtube_url)
            except DownloadError:
                song.title = song.youtube_url

        song.status = SongStatus.DOWNLOADING
        _emit_queue_update(socketio, queue)

        config = KaraokeConfig(
            youtube_url=song.youtube_url,
            output_dir=output_dir / song.song_id,
            output_filename="karaoke",
            separation_model=separation_model,
            vocals_volume=vocals_volume,
            whisper_model=whisper_model,
            track2stem_url=track2stem_url,
            visual_style=visual_style,
        )

        try:
            result = run_pipeline(config)
            song.video_path = result.video_path
            song.status = SongStatus.READY
        except Exception as exc:
            song.status = SongStatus.ERROR
            song.error = str(exc)
        finally:
            _emit_queue_update(socketio, queue)

    queue = SongQueue(worker=process_song)
    queue.start_worker()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    # --- Queue API ---

    @app.route("/api/queue", methods=["GET"])
    def get_queue():
        return jsonify(queue.get_all())

    @app.route("/api/queue", methods=["POST"])
    def add_to_queue():
        data = request.get_json(silent=True) or {}
        url = data.get("url", "").strip()
        if not url:
            abort(400, description="'url' field is required.")
        title = data.get("title", "")

        # Try to prefetch title in the background (non-blocking)
        if not title:
            try:
                info = get_video_info(url)
                title = info.get("title", "")
            except DownloadError:
                title = url

        song = queue.add(url, title=title)
        _emit_queue_update(socketio, queue)
        return jsonify(song.to_dict()), 201

    @app.route("/api/queue/<song_id>", methods=["DELETE"])
    def remove_from_queue(song_id: str):
        removed = queue.remove(song_id)
        if not removed:
            abort(404, description="Song not found or cannot be removed.")
        _emit_queue_update(socketio, queue)
        return jsonify({"removed": song_id})

    @app.route("/api/queue/<song_id>/up", methods=["POST"])
    def move_up(song_id: str):
        queue.move_up(song_id)
        _emit_queue_update(socketio, queue)
        return jsonify(queue.get_all())

    @app.route("/api/queue/<song_id>/down", methods=["POST"])
    def move_down(song_id: str):
        queue.move_down(song_id)
        _emit_queue_update(socketio, queue)
        return jsonify(queue.get_all())

    @app.route("/api/queue/<song_id>", methods=["GET"])
    def get_song(song_id: str):
        song = queue.get_song(song_id)
        if not song:
            abort(404, description="Song not found.")
        return jsonify(song.to_dict())

    # --- Video serving ---

    @app.route("/video/<song_id>")
    def serve_video(song_id: str):
        song = queue.get_song(song_id)
        if not song or not song.video_path or not song.video_path.exists():
            abort(404, description="Video not available.")
        return send_file(str(song.video_path), mimetype="video/mp4")

    # --- Health check ---

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # SocketIO events
    # ------------------------------------------------------------------

    @socketio.on("connect")
    def on_connect():
        emit("queue_update", queue.get_all())

    return app, socketio


def _emit_queue_update(socketio: SocketIO, queue: SongQueue) -> None:
    """Broadcast the current queue state to all connected clients."""
    socketio.emit("queue_update", queue.get_all())
