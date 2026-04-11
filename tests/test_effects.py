"""Tests for yt2karaoke.effects."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
from pathlib import Path

from yt2karaoke.effects import _numpy_fallback_effects, apply_effects_numpy


def _write_sine(path: Path, duration: float = 1.0, sr: int = 22050) -> Path:
    samples = int(duration * sr)
    t = np.linspace(0, duration, samples, dtype=np.float32)
    data = (np.sin(2 * np.pi * 440 * t) * 0.5).reshape(-1, 1)
    sf.write(str(path), data, sr)
    return path


# ---------------------------------------------------------------------------
# _numpy_fallback_effects (pure NumPy, no external deps)
# ---------------------------------------------------------------------------

def test_numpy_effects_returns_same_shape():
    sr = 22050
    data = np.random.randn(sr, 2).astype(np.float32) * 0.3
    result = _numpy_fallback_effects(data, sr)
    assert result.shape == data.shape


def test_numpy_effects_does_not_clip():
    sr = 22050
    data = np.random.randn(sr, 2).astype(np.float32) * 0.5
    result = _numpy_fallback_effects(data, sr)
    assert np.max(np.abs(result)) <= 1.0 + 1e-6


def test_numpy_effects_changes_signal():
    sr = 22050
    data = np.random.randn(sr, 1).astype(np.float32) * 0.1
    result = _numpy_fallback_effects(data, sr, delay_seconds=0.1)
    # Signal should be modified by the delay
    assert not np.allclose(result, data, atol=1e-6)


def test_numpy_effects_zero_delay():
    sr = 22050
    data = np.ones((sr, 1), dtype=np.float32) * 0.2
    # With zero delay feedback the signal should pass through mostly unchanged
    result = _numpy_fallback_effects(data, sr, delay_feedback=0.0, reverb_decay=0.0)
    # Only a small reverb comb filter remains; values near centre should be close
    assert result.shape == data.shape


# ---------------------------------------------------------------------------
# apply_effects_numpy (file-based)
# ---------------------------------------------------------------------------

def test_apply_effects_numpy_produces_file(tmp_path):
    src = _write_sine(tmp_path / "vocals.wav")
    dst = tmp_path / "vocals_fx.wav"
    result = apply_effects_numpy(src, dst)
    assert result.exists()
    assert result == dst


def test_apply_effects_numpy_output_is_valid_audio(tmp_path):
    src = _write_sine(tmp_path / "v.wav")
    dst = tmp_path / "v_fx.wav"
    apply_effects_numpy(src, dst)
    data, sr = sf.read(str(dst))
    assert len(data) > 0
    assert sr == 22050


def test_apply_effects_numpy_creates_parent_dir(tmp_path):
    src = _write_sine(tmp_path / "vocals.wav")
    dst = tmp_path / "deep" / "nested" / "fx.wav"
    apply_effects_numpy(src, dst)
    assert dst.exists()
