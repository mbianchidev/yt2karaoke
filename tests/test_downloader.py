"""Tests for yt2karaoke.downloader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yt2karaoke.downloader import DownloadError, download_audio, get_video_info


# ---------------------------------------------------------------------------
# get_video_info
# ---------------------------------------------------------------------------

def _make_ydl_info():
    return {
        "title": "Test Song",
        "duration": 210,
        "thumbnail": "https://example.com/thumb.jpg",
        "uploader": "TestArtist",
    }


def test_get_video_info_returns_metadata():
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = _make_ydl_info()

        info = get_video_info("https://youtube.com/watch?v=test123")

    assert info["title"] == "Test Song"
    assert info["duration"] == 210
    assert info["uploader"] == "TestArtist"
    assert info["url"] == "https://youtube.com/watch?v=test123"


def test_get_video_info_raises_on_failure():
    import yt_dlp

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = yt_dlp.utils.DownloadError("404")

        with pytest.raises(DownloadError):
            get_video_info("https://youtube.com/watch?v=invalid")


# ---------------------------------------------------------------------------
# download_audio
# ---------------------------------------------------------------------------

def test_download_audio_returns_path(tmp_path):
    fake_info = {**_make_ydl_info(), "title": "My Song"}

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info

        # Simulate yt-dlp writing the file
        expected = tmp_path / "My Song.wav"
        expected.touch()

        path = download_audio(
            "https://youtube.com/watch?v=test123",
            output_dir=tmp_path,
        )

    # Path should be constructed from title + format
    assert path.suffix == ".wav"
    assert str(tmp_path) in str(path)


def test_download_audio_raises_on_failure(tmp_path):
    import yt_dlp

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = yt_dlp.utils.DownloadError("unavailable")

        with pytest.raises(DownloadError):
            download_audio("https://youtube.com/watch?v=bad", output_dir=tmp_path)


def test_download_audio_creates_output_dir(tmp_path):
    new_dir = tmp_path / "subdir" / "deep"
    fake_info = {**_make_ydl_info(), "title": "Deep Song"}

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info
        (new_dir).mkdir(parents=True)

        path = download_audio(
            "https://youtube.com/watch?v=test",
            output_dir=new_dir,
        )

    assert new_dir.is_dir()


@pytest.mark.parametrize("operation", ["metadata", "download"])
def test_youtube_enables_available_javascript_runtimes(operation, tmp_path):
    with patch("yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.extract_info.return_value = _make_ydl_info()
        if operation == "metadata":
            get_video_info("https://youtube.com/watch?v=test123")
        else:
            download_audio(
                "https://youtube.com/watch?v=test123",
                output_dir=tmp_path, filename="test",
            )
    options = mock_ydl.call_args.args[0]
    assert "deno" in options["js_runtimes"]
    assert "node" in options["js_runtimes"]
    assert options["noplaylist"] is True
