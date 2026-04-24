"""Tests for yt2karaoke.player.app (Flask web player)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def app_client():
    """Create a Flask test client with a mocked queue worker."""
    from yt2karaoke.player.app import create_app

    # Patch pipeline.run so no actual processing happens
    with patch("yt2karaoke.player.app.run_pipeline") as mock_run, \
         patch("yt2karaoke.player.app.get_video_info") as mock_info:

        mock_info.return_value = {"title": "Test Song", "duration": 210}
        mock_run.return_value = MagicMock(video_path=None)

        flask_app, socketio = create_app(
            output_dir="/tmp/yt2karaoke_test_output",
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
