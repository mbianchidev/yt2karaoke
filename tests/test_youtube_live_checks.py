"""Deterministic checks for full-song validation and safe preview bounds."""

import json
import struct
from copy import deepcopy

import numpy as np
import pytest
import soundfile as sf

from tests.live.youtube_checks import (
    LiveValidationError,
    lyric_metrics,
    measure_gain,
    preview_excerpt,
    validate_media,
    verify_fast_start,
)
from tests.live import test_youtube_full_song as live_case


def lyrics():
    return [{
        "text": "Original test words",
        "start": 1.0,
        "end": 2.8,
        "words": [
            {"word": "Original", "start": 1.0, "end": 1.5},
            {"word": "test", "start": 1.6, "end": 2.0},
            {"word": "words", "start": 2.2, "end": 2.8},
        ],
    }]


def media():
    return {"streams": [
        {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
         "width": 1280, "height": 720, "r_frame_rate": "24/1",
         "duration": "218.25", "start_time": "0.000000", "nb_frames": "5238"},
        {"codec_type": "audio", "codec_name": "aac", "duration": "218.22"},
    ]}


def test_lyric_metrics_only_return_counts():
    assert lyric_metrics(lyrics(), 3.0) == {"lyric_lines": 1, "timed_words": 3}


@pytest.mark.parametrize("start,end", [
    (-1, 1.5), (1.0, 1.0), (1.0, float("nan")), (1.0, 4.0), (True, 1.5),
])
def test_invalid_word_times_fail_without_echoing_lyrics(start, end):
    data = lyrics()
    data[0]["text"] = "Mock text that must not appear in an error"
    data[0]["words"][0].update(start=start, end=end)
    with pytest.raises(LiveValidationError) as error:
        lyric_metrics(data, 3.0)
    assert data[0]["text"] not in str(error.value)


def test_out_of_order_words_fail():
    data = lyrics()
    data[0]["words"][1]["start"] = 1.1
    with pytest.raises(LiveValidationError, match="order"):
        lyric_metrics(data, 3.0)


def test_preview_is_short_and_does_not_mutate_source():
    data = lyrics()
    original = deepcopy(data)
    chosen, start, end = preview_excerpt(data)
    text = " ".join(word["word"] for word in chosen)
    assert len(text) * 2 + len("In the End") <= 90
    assert end - start <= 5
    assert len(chosen) <= 8
    assert data == original


def test_preview_does_not_include_later_lines():
    data = lyrics()
    data[0]["words"] = [
        {"word": f"word{index}", "start": index * 0.3 + 1, "end": index * 0.3 + 1.2}
        for index in range(20)
    ]
    chosen, start, end = preview_excerpt(data)
    assert len(" ".join(word["word"] for word in chosen)) <= 40
    assert len(chosen) <= 8
    assert end <= data[0]["words"][len(chosen)]["start"]


def test_preview_rejects_an_unusable_first_word():
    data = lyrics()
    data[0]["words"][0]["word"] = "x" * 41
    with pytest.raises(LiveValidationError, match="preview"):
        preview_excerpt(data)


def test_media_validation_accepts_full_length_output():
    result = validate_media(media(), 218.22)
    assert result["codec_name"] == "h264"


@pytest.mark.parametrize("field,value", [
    ("codec_name", "mpeg4"), ("width", 640), ("pix_fmt", "yuv444p"),
    ("duration", "5.0"), ("r_frame_rate", "12/1"),
])
def test_media_validation_rejects_wrong_format_or_truncation(field, value):
    data = media()
    data["streams"][0][field] = value
    with pytest.raises(LiveValidationError):
        validate_media(data, 218.22)


def test_media_validation_requires_audio():
    data = media()
    data["streams"].pop()
    with pytest.raises(LiveValidationError, match="audio"):
        validate_media(data, 218.22)


def test_media_validation_rejects_truncated_audio():
    data = media()
    data["streams"][1]["duration"] = "5.0"
    with pytest.raises(LiveValidationError, match="audio"):
        validate_media(data, 218.22)


def test_fast_start_checks_top_level_boxes(tmp_path):
    path = tmp_path / "test.mp4"
    box = lambda name, data=b"": struct.pack(">I4s", 8 + len(data), name) + data
    path.write_bytes(box(b"ftyp") + box(b"moov") + box(b"mdat"))
    verify_fast_start(path)
    path.write_bytes(box(b"ftyp") + box(b"mdat", b"moov") + box(b"moov"))
    with pytest.raises(LiveValidationError, match="fast-start"):
        verify_fast_start(path)


def test_gain_measurement_preserves_requested_level(tmp_path):
    t = np.arange(16000) / 16000
    backing = np.sin(2 * np.pi * 220 * t) * 0.2
    vocals = np.sin(2 * np.pi * 880 * t) * 0.2
    paths = [tmp_path / name for name in ("base.wav", "mix.wav", "voice.wav")]
    for path, data in zip(paths, (backing, backing + 0.1 * vocals, vocals)):
        sf.write(path, np.column_stack((data, data)), 16000, subtype="FLOAT")
    assert measure_gain(*paths) == pytest.approx(0.1, abs=0.0001)


def test_failed_live_run_reports_failure_and_cleans_private_outputs(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "preview.mp4").write_bytes(b"old generated preview")
    monkeypatch.setenv("YT2KARAOKE_ARTIFACT_DIR", str(artifacts))

    def fail(config, **kwargs):
        raise RuntimeError("Mock transcript content that must not enter the report")

    monkeypatch.setattr(live_case, "run", fail)
    with pytest.raises(RuntimeError):
        live_case.test_full_youtube_song_and_ten_percent_vocal_guide(tmp_path)
    report_text = (artifacts / "report.json").read_text()
    report = json.loads(report_text)
    assert report["result"] == "failed"
    assert report["error_type"] == "RuntimeError"
    assert report["full_source_retained"] is False
    assert "Mock transcript content" not in report_text
    assert not (artifacts / "preview.mp4").exists()
    assert not list(tmp_path.glob("youtube-private-*"))
