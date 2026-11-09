"""Tests for yt2karaoke.player.queue."""

from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

from yt2karaoke.player.queue import SongQueue, SongStatus, QueuedSong


# ---------------------------------------------------------------------------
# Basic queue operations
# ---------------------------------------------------------------------------

def test_add_song():
    q = SongQueue()
    song = q.add("https://youtube.com/watch?v=abc", title="My Song")
    assert song.youtube_url == "https://youtube.com/watch?v=abc"
    assert song.title == "My Song"
    assert song.status == SongStatus.QUEUED
    assert len(q.get_all()) == 1


def test_add_multiple_songs():
    q = SongQueue()
    q.add("https://youtube.com/watch?v=a")
    q.add("https://youtube.com/watch?v=b")
    q.add("https://youtube.com/watch?v=c")
    assert len(q.get_all()) == 3


def test_remove_queued_song():
    q = SongQueue()
    song = q.add("https://youtube.com/watch?v=abc")
    removed = q.remove(song.song_id)
    assert removed is True
    assert len(q.get_all()) == 0


def test_remove_nonexistent_song():
    q = SongQueue()
    removed = q.remove("nonexistent-id")
    assert removed is False


def test_remove_non_queued_song_fails():
    """Songs not in QUEUED state cannot be removed."""
    q = SongQueue()
    song = q.add("https://youtube.com/watch?v=abc")
    song.status = SongStatus.PROCESSING
    removed = q.remove(song.song_id)
    assert removed is False


def test_get_song_returns_correct():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s2 = q.add("https://youtube.com/watch?v=b")
    assert q.get_song(s1.song_id) is s1
    assert q.get_song(s2.song_id) is s2


def test_get_song_returns_none_for_missing():
    q = SongQueue()
    assert q.get_song("missing") is None


def test_next_pending_returns_first_queued():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s2 = q.add("https://youtube.com/watch?v=b")
    assert q.next_pending() is s1


def test_next_pending_skips_non_queued():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s1.status = SongStatus.DONE
    s2 = q.add("https://youtube.com/watch?v=b")
    assert q.next_pending() is s2


def test_next_pending_returns_none_when_empty():
    q = SongQueue()
    assert q.next_pending() is None


# ---------------------------------------------------------------------------
# Move operations
# ---------------------------------------------------------------------------

def test_move_up():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s2 = q.add("https://youtube.com/watch?v=b")
    q.move_up(s2.song_id)
    songs = q.get_all()
    assert songs[0]["id"] == s2.song_id
    assert songs[1]["id"] == s1.song_id


def test_move_up_first_item_is_noop():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    q.add("https://youtube.com/watch?v=b")
    result = q.move_up(s1.song_id)
    assert result is False  # already at top


def test_move_down():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s2 = q.add("https://youtube.com/watch?v=b")
    q.move_down(s1.song_id)
    songs = q.get_all()
    assert songs[0]["id"] == s2.song_id
    assert songs[1]["id"] == s1.song_id


def test_move_down_last_item_is_noop():
    q = SongQueue()
    q.add("https://youtube.com/watch?v=a")
    s2 = q.add("https://youtube.com/watch?v=b")
    result = q.move_down(s2.song_id)
    assert result is False  # already at bottom


@pytest.mark.parametrize("status", [
    SongStatus.DOWNLOADING, SongStatus.PROCESSING, SongStatus.READY, SongStatus.PLAYING,
])
def test_pending_songs_cannot_jump_a_processed_or_active_song(status):
    queue = SongQueue()
    first = queue.add("https://youtube.com/watch?v=first")
    pending = queue.add("https://youtube.com/watch?v=pending")
    first.status = status
    assert queue.move_up(pending.song_id) is False
    first.status, pending.status = SongStatus.QUEUED, status
    assert queue.move_down(first.song_id) is False


def test_queued_vocal_mix_keeps_the_existing_playback_order():
    queue = SongQueue()
    remix = queue.add("https://youtube.com/watch?v=remix")
    pending = queue.add("https://youtube.com/watch?v=pending")
    remix.video_path = Path("instrumental.mp4")
    assert queue.move_down(remix.song_id) is False
    assert queue.move_up(pending.song_id) is False


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def test_worker_processes_song():
    processed = []

    def worker(song: QueuedSong):
        processed.append(song.song_id)
        song.status = SongStatus.READY

    q = SongQueue(worker=worker)
    song = q.add("https://youtube.com/watch?v=test")
    q.start_worker()
    # Give worker time to process
    deadline = time.time() + 5
    while song.status == SongStatus.QUEUED and time.time() < deadline:
        time.sleep(0.05)
    q.stop_worker()

    assert song.song_id in processed
    assert song.status == SongStatus.READY


def test_worker_handles_exception():
    def failing_worker(song: QueuedSong):
        raise ValueError("Processing failed!")

    q = SongQueue(worker=failing_worker)
    song = q.add("https://youtube.com/watch?v=test")
    q.start_worker()

    deadline = time.time() + 5
    while song.status == SongStatus.QUEUED and time.time() < deadline:
        time.sleep(0.05)
    q.stop_worker()

    assert song.status == SongStatus.ERROR
    assert "Processing failed!" in song.error


def test_worker_requires_callable():
    q = SongQueue(worker=None)
    with pytest.raises(RuntimeError):
        q.start_worker()


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------

def test_to_dict_shape():
    q = SongQueue()
    song = q.add("https://youtube.com/watch?v=test", title="Test")
    d = song.to_dict()
    assert d["id"] == song.song_id
    assert d["url"] == "https://youtube.com/watch?v=test"
    assert d["title"] == "Test"
    assert d["status"] == "QUEUED"
    assert d["video_path"] is None
    assert d["error"] is None


def test_current_playing_returns_processing_song():
    q = SongQueue()
    s1 = q.add("https://youtube.com/watch?v=a")
    s1.status = SongStatus.PROCESSING
    assert q.current_playing() is s1


def test_current_playing_returns_none_when_idle():
    q = SongQueue()
    q.add("https://youtube.com/watch?v=a")
    assert q.current_playing() is None
