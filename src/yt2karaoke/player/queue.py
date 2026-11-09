"""Song queue management for the yt2karaoke player."""

from __future__ import annotations

import threading
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional


class SongStatus(Enum):
    QUEUED = auto()
    DOWNLOADING = auto()
    PROCESSING = auto()
    READY = auto()
    PLAYING = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class QueuedSong:
    """A song entry in the playback queue."""

    youtube_url: str
    title: str = ""
    video_path: Optional[Path] = None
    status: SongStatus = SongStatus.QUEUED
    error: Optional[str] = None
    song_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audio_path: Optional[Path] = None
    lyrics_path: Optional[Path] = None
    lyrics_json_path: Optional[Path] = None
    lyrics_lrc_path: Optional[Path] = None
    lyrics_ass_path: Optional[Path] = None
    instrumental_path: Optional[Path] = None
    vocals_path: Optional[Path] = None
    vocals_volume: float = 0.0
    rendered_vocals_volume: float = 0.0
    visual_style: str = "plasma"
    stage: str = "Queued"
    progress: int = 0
    duration: float = 0.0
    mixes: dict[float, Path] = field(default_factory=dict)

    def to_dict(self) -> dict:
        available = self.video_path is not None and self.rendered_vocals_volume in self.mixes
        return {
            "id": self.song_id,
            "url": self.youtube_url,
            "title": self.title,
            "status": self.status.name,
            "video_path": str(self.video_path) if self.video_path else None,
            "error": self.error,
            "source": "upload" if self.audio_path else "youtube",
            "vocals_volume": self.vocals_volume,
            "rendered_vocals_volume": self.rendered_vocals_volume,
            "visual_style": self.visual_style,
            "stage": self.stage,
            "progress": self.progress,
            "duration": self.duration,
            "video_url": (
                f"/video/{self.song_id}?vocals={self.rendered_vocals_volume:g}"
                if available else None
            ),
            "instrumental_url": f"/video/{self.song_id}?vocals=0&download=1" if available else None,
            "mix_url": (
                f"/video/{self.song_id}?vocals={self.rendered_vocals_volume:g}&download=1"
                if available and self.rendered_vocals_volume > 0 else None
            ),
            "lyrics_url": f"/lyrics/{self.song_id}?format=json" if self.lyrics_json_path else None,
        }


class SongQueue:
    """Thread-safe song queue with background processing support.

    Songs are added to the queue and an optional background worker
    processes them one at a time using a user-supplied callback.

    Example::

        def process_song(song: QueuedSong) -> None:
            result = pipeline.run(KaraokeConfig(youtube_url=song.youtube_url))
            song.video_path = result.video_path

        queue = SongQueue(worker=process_song)
        queue.start_worker()
        queue.add("https://youtube.com/watch?v=xxx", title="My Song")
    """

    def __init__(
        self,
        worker: Optional[Callable[[QueuedSong], None]] = None,
    ) -> None:
        self._songs: list[QueuedSong] = []
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._worker = worker
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def add(
        self,
        youtube_url: str,
        title: str = "",
        *,
        audio_path: Optional[Path] = None,
        lyrics_path: Optional[Path] = None,
        vocals_volume: float = 0.0,
        visual_style: str = "plasma",
    ) -> QueuedSong:
        """Add a song to the end of the queue.

        Args:
            youtube_url: YouTube video URL.
            title: Optional display title.

        Returns:
            The newly created :class:`QueuedSong` entry.
        """
        from ..video import validate_vocals_volume

        volume = validate_vocals_volume(vocals_volume)
        if visual_style not in ("plasma", "gradient"):
            raise ValueError("visual_style must be plasma or gradient.")
        song = QueuedSong(
            youtube_url=youtube_url, title=title, audio_path=audio_path,
            lyrics_path=lyrics_path, vocals_volume=volume, visual_style=visual_style,
        )
        with self._lock:
            self._songs.append(song)
        self._event.set()
        return song

    def remove(self, song_id: str) -> bool:
        """Remove a song that is not currently being processed.

        Songs currently being processed cannot be removed.

        Args:
            song_id: The UUID of the song to remove.

        Returns:
            ``True`` if the song was removed, ``False`` if not found or not
            in a removable state.
        """
        with self._lock:
            for i, song in enumerate(self._songs):
                if song.song_id == song_id and song.status in (
                    SongStatus.QUEUED, SongStatus.READY, SongStatus.DONE, SongStatus.ERROR,
                ):
                    self._songs.pop(i)
                    return True
        return False

    def request_mix(self, song_id: str, vocals_volume: float) -> bool:
        """Select a cached mix or queue a separate export using saved stems."""
        from ..video import validate_vocals_volume

        volume = validate_vocals_volume(vocals_volume)
        with self._lock:
            song = next((song for song in self._songs if song.song_id == song_id), None)
            if song is None or song.video_path is None or song.status != SongStatus.READY:
                return False
            song.vocals_volume = volume
            song.error = None
            if volume in song.mixes:
                song.rendered_vocals_volume = volume
                song.stage = "Ready"
                song.progress = 100
            else:
                song.status = SongStatus.QUEUED
                song.stage = "Vocal mix queued"
                song.progress = 0
                self._event.set()
        return True

    def retry(self, song_id: str) -> bool:
        """Retry a failed conversion without losing its source or options."""
        with self._lock:
            song = next((song for song in self._songs if song.song_id == song_id), None)
            if song is None or song.status != SongStatus.ERROR:
                return False
            song.status = SongStatus.QUEUED
            song.stage = "Queued"
            song.progress = 0
            song.error = None
            self._event.set()
        return True

    def update_progress(self, song_id: str, stage: str, progress: int) -> None:
        """Update processing state atomically for queue snapshots."""
        with self._lock:
            for song in self._songs:
                if song.song_id == song_id:
                    song.stage = stage
                    song.progress = progress
                    song.status = (
                        SongStatus.DOWNLOADING if stage == "Downloading audio"
                        else SongStatus.PROCESSING
                    )
                    break

    def move_up(self, song_id: str) -> bool:
        """Move a queued song one position toward the front of the queue."""
        with self._lock:
            for i, song in enumerate(self._songs):
                if song.song_id == song_id and song.status == SongStatus.QUEUED and i > 0:
                    self._songs[i], self._songs[i - 1] = (
                        self._songs[i - 1],
                        self._songs[i],
                    )
                    return True
        return False

    def move_down(self, song_id: str) -> bool:
        """Move a queued song one position toward the back of the queue."""
        with self._lock:
            for i, song in enumerate(self._songs):
                if song.song_id == song_id and song.status == SongStatus.QUEUED and i < len(self._songs) - 1:
                    self._songs[i], self._songs[i + 1] = (
                        self._songs[i + 1],
                        self._songs[i],
                    )
                    return True
        return False

    def get_all(self) -> list[dict]:
        """Return a snapshot of the queue as a list of dicts."""
        with self._lock:
            return [s.to_dict() for s in self._songs]

    def get_song(self, song_id: str) -> Optional[QueuedSong]:
        """Return the :class:`QueuedSong` with *song_id*, or ``None``."""
        with self._lock:
            for song in self._songs:
                if song.song_id == song_id:
                    return song
        return None

    def next_pending(self) -> Optional[QueuedSong]:
        """Return the first song with ``QUEUED`` status."""
        with self._lock:
            for song in self._songs:
                if song.status == SongStatus.QUEUED:
                    return song
        return None

    def current_playing(self) -> Optional[QueuedSong]:
        """Return the song currently in ``PLAYING`` or ``PROCESSING`` state."""
        with self._lock:
            for song in self._songs:
                if song.status in (SongStatus.PLAYING, SongStatus.PROCESSING, SongStatus.DOWNLOADING):
                    return song
        return None

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def start_worker(self) -> None:
        """Start the background processing thread."""
        if self._worker is None:
            raise RuntimeError("No worker callback provided.")
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="yt2karaoke-worker"
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        """Signal the background worker to stop and wait for it to exit."""
        self._running = False
        self._event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self) -> None:
        """Background loop that processes queued songs one at a time."""
        while self._running:
            self._event.wait()
            self._event.clear()
            while self._running:
                with self._lock:
                    song = next((song for song in self._songs if song.status == SongStatus.QUEUED), None)
                    if song is None:
                        break
                    song.status = SongStatus.PROCESSING
                try:
                    self._worker(song)
                    with self._lock:
                        if song.status == SongStatus.PROCESSING:
                            song.status = SongStatus.READY
                except Exception as exc:
                    logging.getLogger(__name__).exception("Processing song %s failed", song.song_id)
                    with self._lock:
                        song.status = SongStatus.ERROR
                        song.error = str(exc)
