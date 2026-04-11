"""Tests for yt2karaoke.transcriber."""

from __future__ import annotations

import pytest

from yt2karaoke.transcriber import (
    LyricLine,
    LyricWord,
    _parse_whisper_result,
    _ass_timestamp,
    lines_to_lrc,
    lines_to_ass,
)


# ---------------------------------------------------------------------------
# _parse_whisper_result
# ---------------------------------------------------------------------------

def _make_whisper_result(segments):
    return {"segments": segments}


def test_parse_empty_result():
    lines = _parse_whisper_result(_make_whisper_result([]))
    assert lines == []


def test_parse_single_segment_no_words():
    result = _make_whisper_result([
        {"text": "Hello world", "start": 0.0, "end": 3.5, "words": []}
    ])
    lines = _parse_whisper_result(result)
    assert len(lines) == 1
    assert lines[0].text == "Hello world"
    assert lines[0].start == 0.0
    assert lines[0].end == 3.5
    assert lines[0].words == []


def test_parse_segment_with_words():
    result = _make_whisper_result([
        {
            "text": "Hello world",
            "start": 0.0,
            "end": 2.0,
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.8},
                {"word": "world", "start": 0.9, "end": 1.8},
            ],
        }
    ])
    lines = _parse_whisper_result(result)
    assert len(lines[0].words) == 2
    assert lines[0].words[0].word == "Hello"
    assert lines[0].words[1].word == "world"


def test_parse_multiple_segments():
    result = _make_whisper_result([
        {"text": "Line one", "start": 0.0, "end": 2.0, "words": []},
        {"text": "Line two", "start": 3.0, "end": 5.0, "words": []},
    ])
    lines = _parse_whisper_result(result)
    assert len(lines) == 2
    assert lines[1].start == 3.0


# ---------------------------------------------------------------------------
# _ass_timestamp
# ---------------------------------------------------------------------------

def test_ass_timestamp_zero():
    assert _ass_timestamp(0.0) == "0:00:00.00"


def test_ass_timestamp_one_minute():
    ts = _ass_timestamp(61.5)
    assert ts == "0:01:01.50"


def test_ass_timestamp_over_hour():
    ts = _ass_timestamp(3661.25)
    assert ts.startswith("1:01:")


# ---------------------------------------------------------------------------
# lines_to_lrc
# ---------------------------------------------------------------------------

def test_lrc_header_present():
    lrc = lines_to_lrc([])
    assert "[by:yt2karaoke]" in lrc


def test_lrc_contains_timestamp():
    lines = [LyricLine(text="Hello world", start=65.0, end=70.0)]
    lrc = lines_to_lrc(lines)
    assert "[01:" in lrc
    assert "Hello world" in lrc


def test_lrc_multiple_lines():
    lines = [
        LyricLine(text="Verse one", start=5.0, end=10.0),
        LyricLine(text="Verse two", start=15.0, end=20.0),
    ]
    lrc = lines_to_lrc(lines)
    assert "Verse one" in lrc
    assert "Verse two" in lrc


# ---------------------------------------------------------------------------
# lines_to_ass
# ---------------------------------------------------------------------------

def test_ass_contains_script_info():
    ass = lines_to_ass([])
    assert "[Script Info]" in ass
    assert "PlayResX: 1280" in ass


def test_ass_custom_resolution():
    ass = lines_to_ass([], width=1920, height=1080)
    assert "PlayResX: 1920" in ass
    assert "PlayResY: 1080" in ass


def test_ass_dialogue_events():
    lines = [LyricLine(text="Karaoke!", start=1.0, end=3.0)]
    ass = lines_to_ass(lines)
    assert "Dialogue:" in ass
    assert "Karaoke!" in ass


def test_ass_karaoke_tags_with_words():
    words = [
        LyricWord(word="Hello", start=1.0, end=1.5),
        LyricWord(word="world", start=1.6, end=2.0),
    ]
    lines = [LyricLine(text="Hello world", start=1.0, end=2.0, words=words)]
    ass = lines_to_ass(lines)
    # Karaoke timing tags should appear
    assert r"\k" in ass


def test_lyric_line_str():
    line = LyricLine(text="Some lyrics", start=0.0, end=2.0)
    assert str(line) == "Some lyrics"
