"""Measure encoded output, vocal gain, and repeated-word lyric sync."""

from __future__ import annotations

import json
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from yt2karaoke.transcriber import LyricLine, LyricWord
from yt2karaoke.video import build_video, remix_video

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")


@pytest.fixture
def media(tmp_path):
    t = np.arange(32000) / 16000
    instrumental, vocals = tmp_path / "instrumental.wav", tmp_path / "vocals.wav"
    sf.write(instrumental, np.sin(2 * np.pi * 220 * t) * 0.2, 16000)
    sf.write(vocals, np.sin(2 * np.pi * 880 * t) * 0.2, 16000)
    lyrics = [LyricLine("go go now", 0.4, 1.7, [
        LyricWord("go", 0.4, 0.7), LyricWord("go", 0.8, 1.1), LyricWord("now", 1.2, 1.7),
    ])]
    video = build_video(
        instrumental, lyrics, tmp_path / "instrumental.mp4",
        width=320, height=180, fps=8, font_size=28,
    )
    return video, instrumental, vocals, tmp_path


def command(*args):
    return subprocess.run(args, capture_output=True, check=True).stdout


def audio(path):
    return np.frombuffer(command(
        "ffmpeg", "-v", "error", "-i", str(path), "-vn",
        "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1",
    ), dtype=np.float32)


def tone_level(samples, frequency):
    samples = samples[4000:28000]
    t = np.arange(len(samples)) / 16000
    return abs(np.mean(samples * np.exp(-2j * np.pi * frequency * t))) * 2


def test_mp4_is_browser_ready(media):
    info = json.loads(command(
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(media[0]),
    ))
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    sound = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
    assert video["codec_name"] == "h264"
    assert video["pix_fmt"] == "yuv420p"
    assert (video["width"], video["height"]) == (320, 180)
    assert sound["codec_name"] == "aac"
    assert abs(float(info["format"]["duration"]) - 2.0) <= 1 / 8
    data = media[0].read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")


def test_instrumental_and_requested_voice_gain(media):
    video, instrumental, vocals, directory = media
    quarter = remix_video(video, instrumental, vocals, directory / "quarter.mp4", 0.25)
    full = remix_video(video, instrumental, vocals, directory / "full.mp4", 1.0)
    baseline, mixed, reference = audio(video), audio(quarter), audio(full)
    assert tone_level(baseline, 880) < tone_level(baseline, 220) * 0.005
    assert tone_level(mixed, 880) / tone_level(reference, 880) == pytest.approx(0.25, abs=0.025)
    assert tone_level(mixed, 220) / tone_level(baseline, 220) == pytest.approx(1.0, abs=0.03)
    for time in ("0.5", "0.875"):
        original_frame = command(
            "ffmpeg", "-v", "error", "-ss", time, "-i", str(video), "-frames:v", "1", "-an", "-f", "md5", "pipe:1",
        )
        mixed_frame = command(
            "ffmpeg", "-v", "error", "-ss", time, "-i", str(quarter), "-frames:v", "1", "-an", "-f", "md5", "pipe:1",
        )
        assert original_frame == mixed_frame


def test_repeated_words_highlight_individually_in_encoded_video(media):
    centers = []
    for time in ("0.5", "0.875"):
        pixels = np.frombuffer(command(
            "ffmpeg", "-v", "error", "-ss", time, "-i", str(media[0]),
            "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ), dtype=np.uint8).reshape(180, 320, 3)
        yellow = (pixels[:, :, 0] > 180) & (pixels[:, :, 1] > 180) & (pixels[:, :, 2] < 90)
        assert yellow.sum() > 10
        centers.append(np.where(yellow)[1].mean())
    assert centers[1] > centers[0] + 15
