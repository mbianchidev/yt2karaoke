"""Regression tests for raw-vocal transcription and separate mix gain."""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from yt2karaoke.pipeline import KaraokeConfig, run
from yt2karaoke.transcriber import LyricLine, LyricWord, TranscriptionError


@pytest.fixture
def pipeline_mocks(tmp_path):
    instrumental = tmp_path / "instrumental.wav"
    vocals = tmp_path / "vocals.wav"
    samples = np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 0.2
    sf.write(instrumental, samples, 16000)
    sf.write(vocals, samples, 16000)
    lyrics = [LyricLine("Original test", 0.1, 0.9, [
        LyricWord("Original", 0.1, 0.4), LyricWord("test", 0.5, 0.9),
    ])]

    def write_video(*args, **kwargs):
        args[2].write_bytes(b"test video")
        return args[2]

    with patch("yt2karaoke.downloader.get_video_info", return_value={"title": "Original test"}), \
         patch("yt2karaoke.downloader.download_audio", return_value=instrumental) as download, \
         patch("yt2karaoke.separator.separate", return_value={
             "instrumental": instrumental, "vocals": vocals,
         }) as separate, \
         patch("yt2karaoke.transcriber.transcribe", return_value=lyrics) as transcribe, \
         patch("yt2karaoke.video.build_video", side_effect=write_video) as build:
        yield {
            "instrumental": instrumental, "vocals": vocals, "lyrics": lyrics,
            "download": download, "separate": separate, "transcribe": transcribe,
            "build": build,
        }


@pytest.mark.parametrize("volume", [0.0, 0.25, 1.0])
def test_transcribes_full_strength_vocals_and_applies_gain_once(tmp_path, pipeline_mocks, volume):
    result = run(KaraokeConfig(
        youtube_url="https://youtube.com/watch?v=synthetic",
        output_dir=tmp_path / "output",
        vocals_volume=volume,
        apply_reverb=False,
        apply_delay=False,
    ))
    pipeline_mocks["separate"].assert_called_once()
    assert pipeline_mocks["separate"].call_args.kwargs["vocals_volume"] == 1.0
    assert pipeline_mocks["transcribe"].call_args.args[0] == pipeline_mocks["vocals"]
    kwargs = pipeline_mocks["build"].call_args.kwargs
    assert kwargs["vocals_volume"] == volume
    assert kwargs["vocals_path"] == (pipeline_mocks["vocals"] if volume else None)
    original, _ = sf.read(pipeline_mocks["vocals"])
    exported, _ = sf.read(result.vocals_path)
    np.testing.assert_array_equal(original, exported)
    assert json.loads(result.lyrics_json_path.read_text())[0]["text"] == "Original test"


def test_local_audio_skips_download(tmp_path, pipeline_mocks):
    run(KaraokeConfig(
        audio_path=pipeline_mocks["instrumental"],
        output_dir=tmp_path / "output",
        title="Original local track",
    ))
    pipeline_mocks["download"].assert_not_called()


def test_timed_lyrics_skip_transcription(tmp_path, pipeline_mocks):
    lyrics_path = tmp_path / "provided.json"
    lyrics_path.write_text(json.dumps([{
        "text": "Original test", "start": 0.1, "end": 0.9,
        "words": [
            {"word": "Original", "start": 0.1, "end": 0.4},
            {"word": "test", "start": 0.5, "end": 0.9},
        ],
    }]))
    result = run(KaraokeConfig(
        audio_path=pipeline_mocks["instrumental"],
        lyrics_path=lyrics_path,
        output_dir=tmp_path / "output",
    ))
    pipeline_mocks["transcribe"].assert_not_called()
    assert result.lyrics_json_path.is_file()


def test_progress_reaches_ready(tmp_path, pipeline_mocks):
    updates = []
    run(KaraokeConfig(
        audio_path=pipeline_mocks["instrumental"],
        output_dir=tmp_path / "output",
    ), on_progress=lambda stage, progress: updates.append((stage, progress)))
    assert updates[0][1] == 0
    assert updates[-1] == ("Ready", 100)
    assert "Separating vocals" in [stage for stage, _ in updates]


@pytest.mark.parametrize("volume", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_gain_is_rejected_before_processing(tmp_path, volume):
    with pytest.raises(ValueError, match="vocals_volume"):
        run(KaraokeConfig(youtube_url="test", output_dir=tmp_path, vocals_volume=volume))


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        run(KaraokeConfig(output_dir=tmp_path))


def test_empty_transcription_is_not_a_success(tmp_path, pipeline_mocks):
    pipeline_mocks["transcribe"].return_value = []
    with pytest.raises(TranscriptionError, match="No lyrics"):
        run(KaraokeConfig(
            audio_path=pipeline_mocks["instrumental"],
            output_dir=tmp_path / "output",
        ))
    pipeline_mocks["build"].assert_not_called()


def test_effects_failure_is_not_silently_ignored(tmp_path, pipeline_mocks):
    with patch("yt2karaoke.effects.apply_effects", side_effect=RuntimeError("effects failed")):
        with pytest.raises(RuntimeError, match="effects failed"):
            run(KaraokeConfig(
                audio_path=pipeline_mocks["instrumental"],
                output_dir=tmp_path / "output",
                vocals_volume=0.25,
            ))


def test_local_source_is_never_overwritten(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original input")
    with pytest.raises(ValueError, match="overwrite an input"):
        run(KaraokeConfig(audio_path=source, output_dir=tmp_path))
    assert source.read_bytes() == b"original input"


def test_supplied_lyrics_are_never_overwritten(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"original input")
    lyrics = tmp_path / "source.lyrics.json"
    lyrics.write_text("original lyrics draft")
    with pytest.raises(ValueError, match="overwrite an input"):
        run(KaraokeConfig(audio_path=source, lyrics_path=lyrics, output_dir=tmp_path))
    assert lyrics.read_text() == "original lyrics draft"
