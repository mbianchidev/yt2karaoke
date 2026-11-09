"""Validation of user-provided word-timed lyrics."""

import json

import pytest

from yt2karaoke.transcriber import TranscriptionError, load_lyrics


def _line():
    return {
        "text": "Original lyrics", "start": 1.0, "end": 2.0,
        "words": [
            {"word": "Original", "start": 1.0, "end": 1.4},
            {"word": "lyrics", "start": 1.5, "end": 2.0},
        ],
    }


def test_load_word_timed_lyrics(tmp_path):
    path = tmp_path / "lyrics.json"
    path.write_text(json.dumps([_line()]))
    lines = load_lyrics(path)
    assert lines[0].text == "Original lyrics"
    assert lines[0].words[1].start == 1.5


@pytest.mark.parametrize("data", [
    [], {}, ["wrong"],
    [{**_line(), "start": -1}],
    [{**_line(), "end": float("nan")}],
    [{**_line(), "start": True}],
    [{**_line(), "words": []}],
    [{**_line(), "text": "does not match words"}],
    [{**_line(), "words": [{"word": "Original lyrics", "start": 0, "end": 2}]}],
    [_line(), _line()],
])
def test_rejects_invalid_lyrics(tmp_path, data):
    path = tmp_path / "lyrics.json"
    path.write_text(json.dumps(data))
    with pytest.raises(TranscriptionError):
        load_lyrics(path)


def test_rejects_invalid_json(tmp_path):
    path = tmp_path / "lyrics.json"
    path.write_text("not JSON")
    with pytest.raises(TranscriptionError, match="JSON"):
        load_lyrics(path)
