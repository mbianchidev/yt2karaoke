"""Tests for yt2karaoke.visuals."""

from __future__ import annotations

import numpy as np
import pytest

from yt2karaoke.visuals import (
    generate_frames,
    render_lyric_frame,
    _render_plasma_numpy,
    _render_gradient_numpy,
)


# ---------------------------------------------------------------------------
# generate_frames
# ---------------------------------------------------------------------------

def test_generate_frames_count():
    frames = list(generate_frames(duration=1.0, fps=5.0, width=64, height=36))
    assert len(frames) == 5


def test_generate_frames_shape():
    for frame in generate_frames(duration=0.5, fps=4.0, width=64, height=36):
        assert frame.shape == (36, 64, 3)
        assert frame.dtype == np.uint8
        break  # check first frame only


def test_generate_frames_gradient_style():
    frames = list(generate_frames(duration=0.5, fps=4.0, width=64, height=36, style="gradient"))
    assert len(frames) == 2
    for f in frames:
        assert f.shape == (36, 64, 3)


def test_generate_frames_plasma_style():
    frames = list(generate_frames(duration=0.5, fps=4.0, width=64, height=36, style="plasma"))
    assert len(frames) == 2
    for f in frames:
        assert f.shape == (36, 64, 3)


# ---------------------------------------------------------------------------
# _render_plasma_numpy
# ---------------------------------------------------------------------------

def test_plasma_valid_rgb():
    import math
    xs = np.linspace(0, 2 * math.pi, 64, dtype=np.float32)
    ys = np.linspace(0, 2 * math.pi, 36, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    frame = _render_plasma_numpy(xg, yg, 0.0, 64, 36)
    assert frame.shape == (36, 64, 3)
    assert frame.dtype == np.uint8
    assert np.all(frame >= 0) and np.all(frame <= 255)


# ---------------------------------------------------------------------------
# _render_gradient_numpy
# ---------------------------------------------------------------------------

def test_gradient_valid_rgb():
    import math
    xs = np.linspace(0, 2 * math.pi, 64, dtype=np.float32)
    ys = np.linspace(0, 2 * math.pi, 36, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    frame = _render_gradient_numpy(xg, yg, 0.0, 64, 36)
    assert frame.shape == (36, 64, 3)
    assert frame.dtype == np.uint8
    assert np.all(frame >= 0) and np.all(frame <= 255)


def test_gradient_changes_over_time():
    import math
    xs = np.linspace(0, 2 * math.pi, 64, dtype=np.float32)
    ys = np.linspace(0, 2 * math.pi, 36, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    f1 = _render_gradient_numpy(xg, yg, 0.0, 64, 36)
    f2 = _render_gradient_numpy(xg, yg, 1.0, 64, 36)
    assert not np.array_equal(f1, f2)


# ---------------------------------------------------------------------------
# render_lyric_frame
# ---------------------------------------------------------------------------

def test_render_lyric_frame_returns_correct_shape():
    bg = np.zeros((72, 128, 3), dtype=np.uint8)
    frame = render_lyric_frame(bg, "Hello world", "", width=128, height=72)
    assert frame.shape == (72, 128, 3)
    assert frame.dtype == np.uint8


def test_render_lyric_frame_empty_text():
    bg = np.zeros((72, 128, 3), dtype=np.uint8)
    frame = render_lyric_frame(bg, "", "", width=128, height=72)
    assert frame.shape == (72, 128, 3)


def test_render_lyric_frame_with_next_line():
    bg = np.zeros((72, 128, 3), dtype=np.uint8)
    frame = render_lyric_frame(bg, "Current line", "Next line", width=128, height=72)
    assert frame.shape == (72, 128, 3)


def test_render_lyric_frame_with_highlighted_word():
    bg = np.zeros((72, 128, 3), dtype=np.uint8)
    frame = render_lyric_frame(
        bg, "Hello world", highlight_word="Hello", width=128, height=72
    )
    assert frame.shape == (72, 128, 3)
