"""Song queue management for the yt2karaoke player."""

from __future__ import annotations

import threading
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

    def to_dict(self) -> dict:
        return {
            "id": self.song_id,
            "url": self.youtube_url,
            "title": self.title,
            "status": self.status.name,
            "video_path": str(self.video_path) if self.video_path else None,
            "error": self.error,
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
        self._current_index: int = -1

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def add(self, youtube_url: str, title: str = "") -> QueuedSong:
        """Add a song to the end of the queue.

        Args:
            youtube_url: YouTube video URL.
            title: Optional display title.

        Returns:
            The newly created :class:`QueuedSong` entry.
        """
        song = QueuedSong(youtube_url=youtube_url, title=title)
        with self._lock:
            self._songs.append(song)
        self._event.set()
        return song

    def remove(self, song_id: str) -> bool:
        """Remove a *QUEUED* song from the queue.

        Songs currently being processed cannot be removed.

        Args:
            song_id: The UUID of the song to remove.

        Returns:
            ``True`` if the song was removed, ``False`` if not found or not
            in a removable state.
        """
        with self._lock:
            for i, song in enumerate(self._songs):
                if song.song_id == song_id and song.status == SongStatus.QUEUED:
                    self._songs.pop(i)
                    return True
        return False

    def move_up(self, song_id: str) -> bool:
        """Move a queued song one position toward the front of the queue."""
        with self._lock:
            for i, song in enumerate(self._songs):
                if song.song_id == song_id and i > 0:
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
                if song.song_id == song_id and i < len(self._songs) - 1:
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
                song = self.next_pending()
                if song is None:
                    break
                song.status = SongStatus.PROCESSING
                try:
                    self._worker(song)
                    if song.status == SongStatus.PROCESSING:
                        song.status = SongStatus.READY
                except Exception as exc:
                    song.status = SongStatus.ERROR
                    song.error = str(exc)
