"""Tests for yt2karaoke.player.app (Flask web player)."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def app_client(tmp_path):
    """Create a Flask test client with a mocked queue worker."""
    from yt2karaoke.player.app import create_app

    # Patch pipeline.run so no actual processing happens
    with patch("yt2karaoke.player.app.run_pipeline") as mock_run, \
         patch("yt2karaoke.player.queue.SongQueue.start_worker"):
        mock_run.return_value = MagicMock(video_path=None)

        flask_app, socketio = create_app(
            output_dir=tmp_path,
            whisper_model="tiny",
        )
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            yield client


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_endpoint(app_client):
    resp = app_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

def test_index_returns_html(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert b"yt2karaoke" in resp.data


# ---------------------------------------------------------------------------
# Queue API
# ---------------------------------------------------------------------------

def test_get_queue_empty(app_client):
    resp = app_client.get("/api/queue")
    assert resp.status_code == 200
    assert resp.json == []


def test_add_to_queue(app_client):
    resp = app_client.post(
        "/api/queue",
        data=json.dumps({"url": "https://youtube.com/watch?v=test123", "title": "Test"}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.json
    assert data["url"] == "https://youtube.com/watch?v=test123"
    assert data["title"] == "Test"
    assert "id" in data


@pytest.mark.parametrize("source", ["youtube", "upload"])
def test_queue_keeps_singer_name(app_client, source):
    if source == "youtube":
        response = app_client.post("/api/queue", json={
            "url": "https://youtube.com/watch?v=synthetic", "performer": "  Test duo  ",
        })
    else:
        response = app_client.post("/api/queue/upload", data={
            "audio": (BytesIO(b"generated audio fixture"), "test.wav"),
            "performer": "  Test duo  ",
        })
    assert response.status_code == 201
    song = app_client.get(f"/api/queue/{response.json['id']}").json
    assert song["performer"] == "Test duo"


@pytest.mark.parametrize("performer", [None, 42, [], "x" * 101])
def test_queue_rejects_invalid_singer_names(app_client, performer):
    response = app_client.post("/api/queue", json={
        "url": "https://youtube.com/watch?v=synthetic", "performer": performer,
    })
    assert response.status_code == 400
    assert "performer" in response.json["error"]


def test_live_playback_uses_instrumental_and_full_strength_vocals(app_client, tmp_path):
    from yt2karaoke.player.queue import SongStatus

    response = app_client.post("/api/queue", json={"url": "https://youtube.com/watch?v=synthetic"})
    song_id = response.json["id"]
    song = app_client.application.extensions["song_queue"].get_song(song_id)
    song.video_path = tmp_path / "karaoke.mp4"
    song.video_path.write_bytes(b"generated video fixture")
    song.instrumental_path = tmp_path / "instrumental.wav"
    song.instrumental_path.write_bytes(b"generated instrumental fixture")
    song.vocals_path = tmp_path / "vocals.wav"
    original_vocals = b"generated full-strength vocal fixture"
    song.vocals_path.write_bytes(original_vocals)
    song.status = SongStatus.READY
    song.rendered_vocals_volume = 0.25
    song.mixes = {0.0: song.video_path, 0.25: tmp_path / "mix.mp4"}
    snapshot = app_client.get(f"/api/queue/{song_id}").json
    assert snapshot["playback_url"] == f"/video/{song_id}?vocals=0"
    stem = app_client.get(snapshot["vocals_audio_url"])
    assert stem.status_code == 200
    assert stem.mimetype == "audio/wav"
    assert stem.data == original_vocals
    partial = app_client.get(snapshot["vocals_audio_url"], headers={"Range": "bytes=0-8"})
    assert partial.status_code == 206
    assert partial.data == original_vocals[:9]
    assert app_client.get(f"/audio/{song_id}/instrumental").data == b"generated instrumental fixture"
    assert app_client.get(f"/audio/{song_id}/unknown").status_code == 400
    song.vocals_path.unlink()
    missing = app_client.get(snapshot["vocals_audio_url"])
    assert missing.status_code == 404
    assert missing.json["error"]


def test_add_to_queue_missing_url(app_client):
    resp = app_client.post(
        "/api/queue",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_get_queue_after_add(app_client):
    app_client.post(
        "/api/queue",
        data=json.dumps({"url": "https://youtube.com/watch?v=aaa", "title": "Song A"}),
        content_type="application/json",
    )
    app_client.post(
        "/api/queue",
        data=json.dumps({"url": "https://youtube.com/watch?v=bbb", "title": "Song B"}),
        content_type="application/json",
    )
    resp = app_client.get("/api/queue")
    assert resp.status_code == 200
    assert len(resp.json) == 2


def test_get_specific_song(app_client):
    add_resp = app_client.post(
        "/api/queue",
        data=json.dumps({"url": "https://youtube.com/watch?v=xyz"}),
        content_type="application/json",
    )
    song_id = add_resp.json["id"]
    resp = app_client.get(f"/api/queue/{song_id}")
    assert resp.status_code == 200
    assert resp.json["id"] == song_id


def test_get_nonexistent_song(app_client):
    resp = app_client.get("/api/queue/does-not-exist")
    assert resp.status_code == 404


def test_remove_queued_song(app_client):
    add_resp = app_client.post(
        "/api/queue",
        data=json.dumps({"url": "https://youtube.com/watch?v=del"}),
        content_type="application/json",
    )
    song_id = add_resp.json["id"]
    del_resp = app_client.delete(f"/api/queue/{song_id}")
    assert del_resp.status_code == 200
    # Queue should now be empty
    resp = app_client.get("/api/queue")
    assert len(resp.json) == 0


def test_remove_nonexistent_song(app_client):
    resp = app_client.delete("/api/queue/no-such-song")
    assert resp.status_code == 404


def test_video_endpoint_not_found(app_client):
    resp = app_client.get("/video/nonexistent-song-id")
    assert resp.status_code == 404


@pytest.mark.parametrize("volume", [0.0, 0.25, 1.0])
def test_queue_keeps_per_song_vocal_percentage(app_client, volume):
    response = app_client.post("/api/queue", json={
        "url": "https://youtube.com/watch?v=synthetic",
        "title": "Generated test track",
        "vocals_volume": volume,
        "visual_style": "gradient",
    })
    assert response.status_code == 201
    assert response.json["vocals_volume"] == volume
    assert response.json["visual_style"] == "gradient"


@pytest.mark.parametrize("volume", [-0.1, 1.1, True, "loud", None])
def test_queue_rejects_invalid_vocal_percentage(app_client, volume):
    response = app_client.post("/api/queue", json={
        "url": "https://youtube.com/watch?v=synthetic",
        "vocals_volume": volume,
    })
    assert response.status_code == 400
    assert "vocals_volume" in response.json["error"]


@pytest.mark.parametrize("data", [[], "invalid", {"url": 123}, {"title": []}])
def test_queue_rejects_malformed_request_with_json(app_client, data):
    response = app_client.post("/api/queue", json=data)
    assert response.status_code == 400
    assert response.json["error"]


def test_queue_rejects_non_youtube_url(app_client):
    response = app_client.post("/api/queue", json={"url": "https://example.com/song"})
    assert response.status_code == 400
    assert "YouTube" in response.json["error"]


def test_upload_adds_local_audio(app_client):
    response = app_client.post("/api/queue/upload", data={
        "audio": (BytesIO(b"generated audio fixture"), "test-track.wav"),
        "title": "Original demo",
        "vocals_volume": "0.25",
        "visual_style": "gradient",
    })
    assert response.status_code == 201
    assert response.json["source"] == "upload"
    assert response.json["title"] == "Original demo"
    assert response.json["vocals_volume"] == 0.25
    queue = app_client.application.extensions["song_queue"]
    song = queue.get_song(response.json["id"])
    assert song.audio_path.is_file()


@pytest.mark.parametrize("filename,content", [
    ("test.exe", b"not audio"),
    ("test.wav", b""),
])
def test_upload_rejects_invalid_audio(app_client, filename, content):
    response = app_client.post("/api/queue/upload", data={
        "audio": (BytesIO(content), filename),
    })
    assert response.status_code == 400
    assert response.json["error"]
    assert app_client.get("/api/queue").json == []


def test_upload_rejects_invalid_timed_lyrics(app_client):
    response = app_client.post("/api/queue/upload", data={
        "audio": (BytesIO(b"generated audio fixture"), "test.wav"),
        "lyrics": (BytesIO(b"not JSON"), "lyrics.json"),
    })
    assert response.status_code == 400
    assert "lyrics" in response.json["error"].lower()


def test_missing_song_mix_returns_json_error(app_client):
    response = app_client.post("/api/queue/missing/mix", json={"vocals_volume": 0.25})
    assert response.status_code == 404
    assert response.json["error"]


def test_ready_song_can_be_removed(app_client):
    from yt2karaoke.player.queue import SongStatus

    response = app_client.post("/api/queue", json={
        "url": "https://youtube.com/watch?v=synthetic", "title": "Original test",
    })
    song_id = response.json["id"]
    app_client.application.extensions["song_queue"].get_song(song_id).status = SongStatus.READY
    assert app_client.delete(f"/api/queue/{song_id}").status_code == 200


def test_studio_assets_are_served(app_client):
    for path in (
        "/stage", "/static/studio.css", "/static/studio.js", "/static/theme.js",
        "/static/audio-mixer.js", "/static/pitch-processor.js", "/static/stage.js",
        "/static/vendor/socket.io.min.js",
    ):
        assert app_client.get(path).status_code == 200
