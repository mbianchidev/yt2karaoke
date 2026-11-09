"""FFmpeg command, validation, atomic output, and resource lifecycle tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt2karaoke.video import VideoError, build_video, remix_video


@pytest.fixture
def encoder():
    process = MagicMock()
    process.stdin.closed = False
    process.stdin.write.side_effect = lambda data: len(data)
    process.stdin.close.side_effect = lambda: setattr(process.stdin, "closed", True)
    process.poll.return_value = None

    def wait(**kwargs):
        process.poll.return_value = 0
        return 0

    process.wait.side_effect = wait

    def start(command, **kwargs):
        Path(command[-1]).write_bytes(b"encoded fixture")
        return process

    probe = MagicMock(returncode=0, stdout="2.0\n", stderr="")
    with patch("yt2karaoke.video.subprocess.run", return_value=probe) as inspect, \
         patch("yt2karaoke.video.subprocess.Popen", side_effect=start) as popen:
        yield process, popen, inspect


def test_instrumental_render_has_no_original_voice(tmp_path, encoder):
    process, popen, _ = encoder
    output = build_video(tmp_path / "instrumental.wav", [], tmp_path / "out.mp4", width=64, height=36, fps=2)
    assert output.read_bytes() == b"encoded fixture"
    command = popen.call_args.args[0]
    assert "-filter_complex" not in command
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"
    assert process.stdin.write.call_count == 4
    assert process.stdin.closed
    process.terminate.assert_not_called()


def test_render_scales_original_voice_once(tmp_path, encoder):
    _, popen, _ = encoder
    build_video(
        tmp_path / "instrumental.wav", [], tmp_path / "out.mp4",
        vocals_path=tmp_path / "vocals.wav", vocals_volume=0.25,
        width=64, height=36, fps=2,
    )
    command = popen.call_args.args[0]
    audio_filter = command[command.index("-filter_complex") + 1]
    assert "volume=0.25" in audio_filter
    assert audio_filter.count("volume=") == 1
    assert "normalize=0" in audio_filter
    assert "latency=true" in audio_filter


def test_render_reports_frame_progress(tmp_path, encoder):
    progress = []
    build_video(
        tmp_path / "instrumental.wav", [], tmp_path / "out.mp4",
        width=64, height=36, fps=2, on_progress=progress.append,
    )
    assert progress == [0, 0.25, 0.5, 0.75, 1]


def test_missing_ffprobe_is_actionable(tmp_path):
    with patch("yt2karaoke.video.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(VideoError, match="ffprobe was not found"):
            build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4")


def test_missing_ffmpeg_is_actionable(tmp_path, encoder):
    with patch("yt2karaoke.video.subprocess.Popen", side_effect=FileNotFoundError):
        with pytest.raises(VideoError, match="ffmpeg was not found"):
            build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4")
    assert not list(tmp_path.glob(".render_*"))


@pytest.mark.parametrize("duration", ["0", "-1", "nan", "inf", "unknown"])
def test_invalid_audio_duration_is_rejected(tmp_path, encoder, duration):
    _, popen, inspect = encoder
    inspect.return_value.stdout = duration
    with pytest.raises(VideoError, match="duration"):
        build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4")
    popen.assert_not_called()


def test_invalid_audio_is_actionable(tmp_path, encoder):
    encoder[2].return_value.returncode = 1
    encoder[2].return_value.stderr = "invalid audio data"
    with pytest.raises(VideoError, match="invalid audio data"):
        build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4")


@pytest.mark.parametrize("kwargs", [
    {"width": 63}, {"height": 35}, {"fps": 0}, {"fps": float("nan")},
    {"font_size": 0}, {"visual_style": "unknown"}, {"vocals_volume": 0.25},
])
def test_invalid_render_options_fail_before_encoding(tmp_path, kwargs):
    with pytest.raises(VideoError):
        build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4", **kwargs)


def test_frame_error_stops_owned_encoder_and_keeps_existing_output(tmp_path, encoder):
    process, _, _ = encoder
    output = tmp_path / "out.mp4"
    output.write_bytes(b"previous successful export")
    with patch("yt2karaoke.video._FrameGenerator.make_frame", side_effect=ValueError("frame failed")):
        with pytest.raises(ValueError, match="frame failed"):
            build_video(tmp_path / "input.wav", [], output, width=64, height=36, fps=2)
    assert output.read_bytes() == b"previous successful export"
    process.terminate.assert_called_once()
    assert process.stdin.closed
    assert not list(tmp_path.glob(".render_*"))


def test_broken_pipe_reports_encoder_error(tmp_path, encoder):
    process, popen, _ = encoder
    process.stdin.write.side_effect = BrokenPipeError("encoder stopped")
    with pytest.raises(VideoError, match="encoder stopped"):
        build_video(tmp_path / "input.wav", [], tmp_path / "out.mp4", width=64, height=36, fps=2)
    assert process.stdin.closed
    assert not list(tmp_path.glob(".render_*"))


def test_mix_never_overwrites_instrumental(tmp_path):
    video = tmp_path / "original.mp4"
    video.write_bytes(b"original")
    with pytest.raises(VideoError, match="must not overwrite"):
        remix_video(video, tmp_path / "instrumental.wav", tmp_path / "vocals.wav", video, 0.25)
    assert video.read_bytes() == b"original"
