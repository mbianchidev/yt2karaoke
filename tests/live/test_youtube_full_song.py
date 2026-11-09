"""Opt-in real YouTube-to-karaoke regression for the complete source song."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import pytest
import soundfile as sf

from yt2karaoke.pipeline import KaraokeConfig, run
from yt2karaoke.video import remix_video

from .youtube_checks import (
    LiveValidationError,
    decode_audio,
    lyric_metrics,
    make_preview,
    measure_gain,
    probe,
    require,
    validate_media,
    verify_fast_start,
    video_hash,
)

pytestmark = pytest.mark.live_youtube
SOURCE_URL = "https://www.youtube.com/watch?v=eVTXPUF4Oz4"


def test_full_youtube_song_and_ten_percent_vocal_guide(tmp_path):
    artifacts = Path(os.environ.get("YT2KARAOKE_ARTIFACT_DIR", tmp_path / "artifacts"))
    artifacts.mkdir(parents=True, exist_ok=True)
    report_path = artifacts / "report.json"
    report = {
        "source_url": SOURCE_URL,
        "revision": os.environ.get("GITHUB_SHA"),
        "python": platform.python_version(),
        "yt_dlp": version("yt-dlp"),
        "yt_dlp_ejs": version("yt-dlp-ejs"),
        "whisper_model": "small",
        "mocked_services": False,
        "prewritten_lyrics": False,
        "full_media_uploaded": False,
        "transcript_accuracy_reference_checked": False,
        "result": "running",
        "stage": "Starting full-song pipeline",
        "progress": 0,
    }
    work = None

    def save_report():
        temporary = report_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(report_path)

    def progress(stage, percent):
        report.update(stage=stage, progress=percent)
        save_report()

    save_report()
    try:
        (artifacts / "preview.mp4").unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="youtube-private-", dir=tmp_path) as directory:
            work = Path(directory)
            result = run(KaraokeConfig(
                youtube_url=SOURCE_URL,
                output_dir=work,
                output_filename="karaoke",
                whisper_model="small",
                vocals_volume=0.0,
                apply_reverb=False,
                apply_delay=False,
            ), on_progress=progress)
            progress("Checking full-song timing and exports", 100)
            require(abs(result.duration - 218.0) <= 2.0,
                    f"Expected the complete 218-second recording, got {result.duration:.2f} seconds.")
            require(result.lyrics_json_path is not None, "No word-timed JSON was exported.")
            lyrics = json.loads(result.lyrics_json_path.read_text(encoding="utf-8"))
            metrics = lyric_metrics(lyrics, result.duration)
            require(metrics["timed_words"] >= 250,
                    f"The full song produced only {metrics['timed_words']} timed words.")
            require(metrics["lyric_lines"] >= 10,
                    f"The full song produced only {metrics['lyric_lines']} lyric lines.")
            for name, path in (("LRC", result.lyrics_lrc_path), ("ASS", result.lyrics_ass_path)):
                require(path is not None and path.is_file() and path.stat().st_size > 0,
                        f"The {name} export is missing or empty.")
            baseline_info = probe(result.video_path)
            baseline_video = validate_media(baseline_info, result.duration)
            verify_fast_start(result.video_path)
            report.update(
                metrics, title=result.title, duration_seconds=result.duration,
                video={"width": 1280, "height": 720, "fps": 24, "codec": "h264", "audio": "aac"},
                rendered_frames=int(baseline_video["nb_frames"]),
            )
            progress("Checking the full 10% vocal mix", 100)
            guide_path = remix_video(
                result.video_path, result.instrumental_path, result.vocals_path,
                work / "guide-10pct.mp4", 0.1,
            )
            guide_video = validate_media(probe(guide_path), result.duration)
            verify_fast_start(guide_path)
            require(video_hash(result.video_path) == video_hash(guide_path),
                    "The vocal remix changed the synchronized video stream.")
            for field in ("start_time", "duration", "nb_frames"):
                require(guide_video[field] == baseline_video[field],
                        f"The vocal remix changed video {field}.")
            rate = sf.info(result.vocals_path).samplerate
            decoded_base, decoded_guide = work / "decoded-base.wav", work / "decoded-guide.wav"
            decode_audio(result.video_path, decoded_base, rate)
            decode_audio(guide_path, decoded_guide, rate)
            gain = measure_gain(decoded_base, decoded_guide, result.vocals_path)
            require(abs(gain - 0.1) <= 0.015, f"Expected a 0.10 vocal gain, measured {gain:.5f}.")
            report.update(requested_vocal_gain=0.1, measured_vocal_gain=gain, video_stream_unchanged=True)
            progress("Creating the bounded artifact preview", 100)
            report["preview"] = make_preview(result, lyrics, artifacts / "preview.mp4", work)
        report.update(result="passed", stage="Complete", full_source_retained=False)
    finally:
        error = sys.exception()
        if error is not None:
            report.update(result="failed", error_type=type(error).__name__)
            if isinstance(error, LiveValidationError):
                report["error"] = str(error)
        report["full_source_retained"] = work is not None and work.exists()
        save_report()
