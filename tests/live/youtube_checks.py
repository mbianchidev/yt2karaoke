"""Technical media checks that never include transcript text in diagnostics."""

from __future__ import annotations

import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from yt2karaoke.pipeline import KaraokeResult
from yt2karaoke.transcriber import LyricLine, LyricWord
from yt2karaoke.video import build_video


class LiveValidationError(AssertionError):
    """An actionable, transcript-free validation failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveValidationError(message)


def _time(value) -> bool:
    return (
        not isinstance(value, bool) and isinstance(value, (int, float))
        and math.isfinite(value) and value >= 0
    )


def lyric_metrics(lines: list, duration: float) -> dict[str, int]:
    require(isinstance(lines, list) and bool(lines), "No automatic lyric lines were produced.")
    count = 0
    previous_line_end = 0.0
    for index, line in enumerate(lines):
        require(isinstance(line, dict), f"Invalid lyric line at index {index}.")
        start, end = line.get("start"), line.get("end")
        require(_time(start) and _time(end) and start < end <= duration + 0.05,
                f"Invalid interval for lyric line {index}.")
        require(start >= previous_line_end - 0.05, f"Lyric line {index} is out of order.")
        require(isinstance(line.get("text"), str) and bool(line["text"].strip()),
                f"Lyric line {index} has no text.")
        words = line.get("words")
        require(isinstance(words, list) and bool(words), f"Lyric line {index} has no timed words.")
        previous_word_end = start
        for word_index, word in enumerate(words):
            label = f"line {index}, word {word_index}"
            require(isinstance(word, dict), f"Invalid word at {label}.")
            begin, finish = word.get("start"), word.get("end")
            require(_time(begin) and _time(finish) and begin < finish <= duration + 0.05,
                    f"Invalid word interval at {label}.")
            require(begin >= start - 0.05 and finish <= end + 0.05,
                    f"Word interval {begin:.2f}..{finish:.2f}s lies outside "
                    f"line interval {start:.2f}..{end:.2f}s at {label}.")
            require(begin >= previous_word_end - 0.05, f"Word timing is out of order at {label}.")
            require(isinstance(word.get("word"), str) and bool(word["word"].strip()),
                    f"Missing word text at {label}.")
            previous_word_end = finish
            count += 1
        previous_line_end = end
    return {"lyric_lines": len(lines), "timed_words": count}


def preview_excerpt(lines: list) -> tuple[list[dict], float, float]:
    words = [word for line in lines for word in line["words"]]
    require(bool(words), "No words are available for the bounded preview.")
    start = max(0.0, words[0]["start"] - 0.2)
    chosen = []
    for word in words:
        text = " ".join(entry["word"] for entry in chosen + [word])
        if len(text) > 40 or len(chosen) >= 8 or word["end"] - start > 4.8:
            break
        chosen.append(word)
    require(bool(chosen), "The first words cannot form a bounded preview.")
    end = chosen[-1]["end"]
    if len(words) > len(chosen):
        end = min(end, words[len(chosen)]["start"])
    require(start < end <= start + 5, "Invalid bounded preview duration.")
    return chosen, start, end


def command(*args: str) -> bytes:
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise LiveValidationError(f"{args[0]} failed with exit {result.returncode}: {detail}")
    return result.stdout


def probe(path: Path) -> dict:
    return json.loads(command(
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ))


def validate_media(info: dict, duration: float) -> dict:
    video = next((stream for stream in info["streams"] if stream["codec_type"] == "video"), None)
    audio = next((stream for stream in info["streams"] if stream["codec_type"] == "audio"), None)
    require(video is not None, "The MP4 has no video stream.")
    require(audio is not None, "The MP4 has no audio stream.")
    require(video["codec_name"] == "h264", "The video must use H.264.")
    require(video["pix_fmt"] == "yuv420p", "The video must use yuv420p.")
    require((video["width"], video["height"]) == (1280, 720), "Expected a 1280x720 video.")
    require(video["r_frame_rate"] == "24/1", "Expected a 24 fps video.")
    require(audio["codec_name"] == "aac", "The audio must use AAC.")
    require(abs(float(audio["duration"]) - duration) <= 0.1,
            "The audio does not cover the full source duration.")
    require(abs(float(video["duration"]) - duration) <= 1 / 24 + 0.02,
            "The video does not cover the full source duration.")
    require(int(video["nb_frames"]) >= math.floor(duration * 24) - 1,
            "The video is missing source frames.")
    return video


def verify_fast_start(path: Path) -> None:
    with path.open("rb") as source:
        while header := source.read(8):
            require(len(header) == 8, "Invalid MP4 box header.")
            size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if size == 1:
                extended = source.read(8)
                require(len(extended) == 8, "Invalid extended MP4 box.")
                size = struct.unpack(">Q", extended)[0]
                header_size = 16
            if kind == b"moov":
                return
            require(kind != b"mdat", "The MP4 is missing fast-start metadata ordering.")
            require(size >= header_size, "Invalid MP4 box size.")
            source.seek(size - header_size, 1)
    raise LiveValidationError("The MP4 has no fast-start movie metadata.")


def video_hash(path: Path) -> bytes:
    return command(
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
        "-map", "0:v:0", "-c:v", "copy", "-f", "hash", "-hash", "sha256", "pipe:1",
    ).strip()


def decode_audio(path: Path, output: Path, rate: int) -> None:
    command(
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(path),
        "-vn", "-ar", str(rate), "-ac", "2", "-c:a", "pcm_f32le", str(output),
    )


def measure_gain(baseline: Path, mixed: Path, vocals: Path) -> float:
    numerator = denominator = 0.0
    with sf.SoundFile(baseline) as backing, sf.SoundFile(mixed) as guide, sf.SoundFile(vocals) as voice:
        require(backing.samplerate == guide.samplerate == voice.samplerate,
                "The decoded audio sample rates differ.")
        require(backing.channels == guide.channels == voice.channels,
                "The decoded audio channel counts differ.")
        require(min(backing.frames, guide.frames) >= voice.frames - 2048,
                "The decoded audio is truncated.")
        while True:
            chunks = [
                audio.read(65536, dtype="float32", always_2d=True)
                for audio in (backing, guide, voice)
            ]
            length = min(len(chunk) for chunk in chunks)
            if not length:
                break
            base, mix, reference = (chunk[:length] for chunk in chunks)
            numerator += float(np.sum((mix - base) * reference, dtype=np.float64))
            denominator += float(np.sum(reference ** 2, dtype=np.float64))
    require(math.isfinite(denominator) and denominator > 0, "No usable original-vocal signal was found.")
    gain = numerator / denominator
    require(math.isfinite(gain), "The measured vocal gain is not finite.")
    return gain


def make_preview(result: KaraokeResult, lyrics: list, output: Path, work: Path) -> dict:
    chosen, start, end = preview_excerpt(lyrics)
    text = " ".join(word["word"] for word in chosen)
    require(len(text) * 2 + len("In the End") <= 90, "The preview quotation exceeds its bound.")
    with sf.SoundFile(result.instrumental_path) as source:
        rate = source.samplerate
        first_sample, last_sample = math.floor(start * rate), math.floor(end * rate)
        source.seek(first_sample)
        backing = source.read(last_sample - first_sample, dtype="float32", always_2d=True)
    with sf.SoundFile(result.vocals_path) as source:
        require(source.samplerate == rate, "The separated stems have different sample rates.")
        source.seek(first_sample)
        voice = source.read(len(backing), dtype="float32", always_2d=True)
    length = min(len(backing), len(voice))
    duration, actual_start = length / rate, first_sample / rate
    require(0 < duration <= 5, "The preview must be at most five seconds.")
    words = [
        LyricWord(word["word"], max(0, word["start"] - actual_start),
                  min(duration, word["end"] - actual_start))
        for word in chosen
    ]
    require(all(word.start < word.end for word in words), "The preview has an invalid word interval.")
    backing_path, voice_path = work / "preview-backing.wav", work / "preview-voice.wav"
    sf.write(backing_path, backing[:length], rate, subtype="FLOAT")
    sf.write(voice_path, voice[:length], rate, subtype="FLOAT")
    build_video(
        backing_path, [LyricLine(text, words[0].start, duration, words)], output,
        vocals_path=voice_path, vocals_volume=0.1,
    )
    validate_media(probe(output), duration)
    verify_fast_start(output)
    return {"duration_seconds": duration, "lyric_characters": len(text), "vocal_gain": 0.1}
