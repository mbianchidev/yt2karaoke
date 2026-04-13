"""Tests for yt2karaoke.video (build_video)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from yt2karaoke.video import VideoError, build_video


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_audio_clip(duration: float = 3.0):
    clip = MagicMock()
    clip.duration = duration
    clip.volumex = MagicMock(return_value=MagicMock(close=MagicMock()))
    clip.close = MagicMock()
    return clip


def _make_mock_video_clip():
    clip = MagicMock()
    clip.set_fps = MagicMock(return_value=clip)
    clip.set_audio = MagicMock(return_value=clip)
    clip.write_videofile = MagicMock()
    clip.close = MagicMock()
    return clip


def _patch_moviepy(inst_clip, video_clip, composite_clip=None, vocals_raw_clip=None):
    """Return a mock ``moviepy.editor`` module suitable for patching."""
    mock_editor = MagicMock()

    if vocals_raw_clip is not None:
        def audio_file_clip_factory(path):
            if "vocals" in str(path):
                return vocals_raw_clip
            return inst_clip
        mock_editor.AudioFileClip = MagicMock(side_effect=audio_file_clip_factory)
    else:
        mock_editor.AudioFileClip = MagicMock(return_value=inst_clip)

    mock_editor.VideoClip = MagicMock(return_value=video_clip)
    mock_editor.CompositeAudioClip = MagicMock(
        return_value=composite_clip if composite_clip is not None else MagicMock()
    )
    return mock_editor


# ---------------------------------------------------------------------------
# ImportError path
# ---------------------------------------------------------------------------

def test_build_video_raises_video_error_when_moviepy_missing(tmp_path):
    """VideoError is raised when moviepy cannot be imported."""
    output_path = tmp_path / "karaoke.mp4"
    instrumental_path = tmp_path / "inst.wav"
    instrumental_path.touch()

    broken_modules = {k: v for k, v in sys.modules.items()}
    broken_modules["moviepy"] = None
    broken_modules["moviepy.editor"] = None

    with patch.dict(sys.modules, broken_modules):
        with pytest.raises(VideoError, match="moviepy is not installed"):
            build_video(instrumental_path, [], output_path)


# ---------------------------------------------------------------------------
# Happy path — instrumental only (no vocals)
# ---------------------------------------------------------------------------

def test_build_video_instrumental_only(tmp_path):
    """build_video returns the output path when no vocals are provided."""
    output_path = tmp_path / "karaoke.mp4"
    instrumental_path = tmp_path / "instrumental.wav"
    instrumental_path.touch()

    inst_clip = _make_mock_audio_clip(duration=5.0)
    video_clip = _make_mock_video_clip()
    mock_editor = _patch_moviepy(inst_clip, video_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        result = build_video(
            instrumental_path,
            [],
            output_path,
            width=64,
            height=36,
            fps=5.0,
        )

    assert result == output_path
    # No CompositeAudioClip needed — single audio track
    mock_editor.CompositeAudioClip.assert_not_called()


# ---------------------------------------------------------------------------
# Vocals mixing — volumex applied with correct gain
# ---------------------------------------------------------------------------

def test_build_video_applies_vocals_volume(tmp_path):
    """When vocals_path is given, AudioFileClip.volumex is called with vocals_volume."""
    output_path = tmp_path / "out.mp4"
    instrumental_path = tmp_path / "inst.wav"
    vocals_path = tmp_path / "vocals.wav"
    instrumental_path.touch()
    vocals_path.touch()

    inst_clip = _make_mock_audio_clip(duration=3.0)
    vocals_raw_clip = MagicMock()
    vocals_scaled_clip = MagicMock(close=MagicMock())
    vocals_raw_clip.volumex = MagicMock(return_value=vocals_scaled_clip)
    video_clip = _make_mock_video_clip()
    mock_editor = _patch_moviepy(inst_clip, video_clip, vocals_raw_clip=vocals_raw_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        build_video(
            instrumental_path,
            [],
            output_path,
            width=64,
            height=36,
            fps=5.0,
            vocals_path=vocals_path,
            vocals_volume=0.5,
        )

    vocals_raw_clip.volumex.assert_called_once_with(0.5)
    mock_editor.CompositeAudioClip.assert_called_once()


# ---------------------------------------------------------------------------
# Resource cleanup — clips are closed
# ---------------------------------------------------------------------------

def test_build_video_closes_clips_after_write(tmp_path):
    """Instrumental and video clips are closed in the finally block."""
    output_path = tmp_path / "out.mp4"
    instrumental_path = tmp_path / "inst.wav"
    instrumental_path.touch()

    inst_clip = _make_mock_audio_clip(duration=2.0)
    video_clip = _make_mock_video_clip()
    mock_editor = _patch_moviepy(inst_clip, video_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        build_video(
            instrumental_path,
            [],
            output_path,
            width=64,
            height=36,
            fps=5.0,
        )

    inst_clip.close.assert_called_once()
    video_clip.close.assert_called_once()


def test_build_video_closes_vocals_clip_after_write(tmp_path):
    """The vocals clip is closed in the finally block when provided."""
    output_path = tmp_path / "out.mp4"
    instrumental_path = tmp_path / "inst.wav"
    vocals_path = tmp_path / "vocals.wav"
    instrumental_path.touch()
    vocals_path.touch()

    inst_clip = _make_mock_audio_clip(duration=2.0)
    vocals_raw_clip = MagicMock()
    vocals_scaled_clip = MagicMock(close=MagicMock())
    vocals_raw_clip.volumex = MagicMock(return_value=vocals_scaled_clip)
    video_clip = _make_mock_video_clip()
    mock_editor = _patch_moviepy(inst_clip, video_clip, vocals_raw_clip=vocals_raw_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        build_video(
            instrumental_path,
            [],
            output_path,
            width=64,
            height=36,
            fps=5.0,
            vocals_path=vocals_path,
            vocals_volume=0.8,
        )

    vocals_scaled_clip.close.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling — write failure raises VideoError
# ---------------------------------------------------------------------------

def test_build_video_raises_on_write_failure(tmp_path):
    """A failed write_videofile call raises VideoError."""
    output_path = tmp_path / "out.mp4"
    instrumental_path = tmp_path / "inst.wav"
    instrumental_path.touch()

    inst_clip = _make_mock_audio_clip(duration=2.0)
    video_clip = _make_mock_video_clip()
    video_clip.write_videofile.side_effect = RuntimeError("encoder error")
    mock_editor = _patch_moviepy(inst_clip, video_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        with pytest.raises(VideoError, match="Failed to write video"):
            build_video(
                instrumental_path,
                [],
                output_path,
                width=64,
                height=36,
                fps=5.0,
            )


# ---------------------------------------------------------------------------
# Error handling — vocals load failure raises VideoError
# ---------------------------------------------------------------------------

def test_build_video_raises_on_vocals_load_failure(tmp_path):
    """A failed vocals AudioFileClip load raises VideoError."""
    output_path = tmp_path / "out.mp4"
    instrumental_path = tmp_path / "inst.wav"
    vocals_path = tmp_path / "vocals.wav"
    instrumental_path.touch()
    vocals_path.touch()

    inst_clip = _make_mock_audio_clip(duration=2.0)
    vocals_raw_clip = MagicMock()
    vocals_raw_clip.volumex.side_effect = OSError("file not found")
    video_clip = _make_mock_video_clip()
    mock_editor = _patch_moviepy(inst_clip, video_clip, vocals_raw_clip=vocals_raw_clip)

    with patch.dict(sys.modules, {"moviepy.editor": mock_editor}):
        with pytest.raises(VideoError, match="Failed to load vocals audio"):
            build_video(
                instrumental_path,
                [],
                output_path,
                width=64,
                height=36,
                fps=5.0,
                vocals_path=vocals_path,
                vocals_volume=0.5,
            )
