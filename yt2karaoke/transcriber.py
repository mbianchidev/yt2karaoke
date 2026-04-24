"""Lyrics transcription and karaoke-style timestamp generation.

Uses OpenAI Whisper to transcribe vocals and produce word-level timestamps
suitable for karaoke sync.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LyricLine:
    """A single line of lyrics with timing information."""

    text: str
    start: float  # seconds
    end: float    # seconds
    words: list["LyricWord"] = field(default_factory=list)

    def __str__(self) -> str:
        return self.text


@dataclass
class LyricWord:
    """A single word within a lyric line."""

    word: str
    start: float  # seconds
    end: float    # seconds


class TranscriptionError(Exception):
    """Raised when transcription fails."""


def transcribe(
    vocals_path: str | os.PathLike,
    model_size: str = "base",
    language: Optional[str] = None,
) -> list[LyricLine]:
    """Transcribe vocals and return time-stamped lyric lines.

    Args:
        vocals_path: Path to the vocals audio file (WAV/MP3/FLAC).
        model_size: Whisper model size: tiny, base, small, medium, large.
            Larger models are more accurate but slower.
        language: Optional ISO-639-1 language code (e.g. "en", "es").
            When *None*, Whisper auto-detects the language.

    Returns:
        List of :class:`LyricLine` objects ordered by start time.

    Raises:
        TranscriptionError: If Whisper is not installed or transcription fails.
    """
    try:
        import whisper
    except ImportError as exc:
        raise TranscriptionError(
            "openai-whisper is not installed.  Run: pip install openai-whisper"
        ) from exc

    vocals_path = Path(vocals_path)
    if not vocals_path.exists():
        raise TranscriptionError(f"Vocals file not found: {vocals_path}")

    model = whisper.load_model(model_size)
    options: dict = {
        "word_timestamps": True,
        "verbose": False,
    }
    if language:
        options["language"] = language

    try:
        result = model.transcribe(str(vocals_path), **options)
    except Exception as exc:
        raise TranscriptionError(f"Whisper transcription failed: {exc}") from exc

    return _parse_whisper_result(result)


def _parse_whisper_result(result: dict) -> list[LyricLine]:
    """Convert a raw Whisper result dict into :class:`LyricLine` objects."""
    lines: list[LyricLine] = []

    for segment in result.get("segments", []):
        words: list[LyricWord] = []
        for w in segment.get("words", []):
            words.append(
                LyricWord(
                    word=w.get("word", "").strip(),
                    start=float(w.get("start", 0.0)),
                    end=float(w.get("end", 0.0)),
                )
            )
        line = LyricLine(
            text=segment.get("text", "").strip(),
            start=float(segment.get("start", 0.0)),
            end=float(segment.get("end", 0.0)),
            words=words,
        )
        lines.append(line)

    return lines


def lines_to_lrc(lines: list[LyricLine]) -> str:
    """Serialize lyric lines to LRC format.

    LRC is a plain-text lyrics format supported by many media players.

    Args:
        lines: List of :class:`LyricLine` objects.

    Returns:
        LRC-formatted string.
    """
    lrc_lines = ["[by:yt2karaoke]"]
    for line in lines:
        mm = int(line.start // 60)
        ss = line.start - mm * 60
        lrc_lines.append(f"[{mm:02d}:{ss:05.2f}]{line.text}")
    return "\n".join(lrc_lines)


def lines_to_ass(lines: list[LyricLine], width: int = 1280, height: int = 720) -> str:
    """Serialize lyric lines to ASS (Advanced SubStation Alpha) subtitle format.

    The ASS format supports per-word highlighting (karaoke tags), making it
    ideal for karaoke-style display with software like VLC or ffmpeg.

    Args:
        lines: List of :class:`LyricLine` objects.
        width: Video width in pixels.
        height: Video height in pixels.

    Returns:
        ASS-formatted string.
    """
    header = f"""[Script Info]
Title: yt2karaoke
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,52,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        start_ts = _ass_timestamp(line.start)
        end_ts = _ass_timestamp(line.end)
        if line.words:
            # Build karaoke tagged text for word-by-word highlighting
            tagged_parts = []
            for word in line.words:
                duration_cs = int((word.end - word.start) * 100)  # centiseconds
                tagged_parts.append(f"{{\\k{duration_cs}}}{word.word} ")
            text = "".join(tagged_parts).rstrip()
        else:
            text = line.text
        events.append(
            f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{text}"
        )

    return header + "\n".join(events) + "\n"


def _ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp string (H:MM:SS.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"
