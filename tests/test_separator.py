"""Tests for yt2karaoke.separator."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

from yt2karaoke.separator import (
    SeparationError,
    _mix_stems,
    _scale_audio,
    Track2StemClient,
)


# ---------------------------------------------------------------------------
# _mix_stems
# ---------------------------------------------------------------------------

def _write_wav(path: Path, duration: float = 1.0, sr: int = 22050) -> Path:
    """Write a simple sine-wave WAV file for testing."""
    samples = int(duration * sr)
    t = np.linspace(0, duration, samples, dtype=np.float32)
    data = (np.sin(2 * np.pi * 440 * t) * 0.5).reshape(-1, 1)
    sf.write(str(path), data, sr)
    return path


def test_mix_stems_produces_output(tmp_path):
    p1 = _write_wav(tmp_path / "drums.wav")
    p2 = _write_wav(tmp_path / "bass.wav")
    out = tmp_path / "mix.wav"

    _mix_stems([p1, p2], out)

    assert out.exists()
    data, _ = sf.read(str(out))
    assert len(data) > 0


def test_mix_stems_single_stem(tmp_path):
    p1 = _write_wav(tmp_path / "other.wav")
    out = tmp_path / "mix.wav"
    _mix_stems([p1], out)
    assert out.exists()


def test_mix_stems_empty_raises():
    with pytest.raises(SeparationError):
        _mix_stems([], Path("/tmp/nowhere.wav"))


def test_mix_stems_normalises_output(tmp_path):
    """Mixed output should not clip (max abs ≤ 1)."""
    p1 = _write_wav(tmp_path / "a.wav")
    p2 = _write_wav(tmp_path / "b.wav")
    out = tmp_path / "mix.wav"
    _mix_stems([p1, p2], out)
    data, _ = sf.read(str(out), dtype="float32")
    assert np.max(np.abs(data)) <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# _scale_audio
# ---------------------------------------------------------------------------

def test_scale_audio_half_volume(tmp_path):
    src = _write_wav(tmp_path / "vocals.wav")
    dst = tmp_path / "vocals_scaled.wav"
    _scale_audio(src, dst, 0.5)
    orig, _ = sf.read(str(src), dtype="float32")
    scaled, _ = sf.read(str(dst), dtype="float32")
    # Use atol=1e-4 to account for float32 WAV quantisation round-trip errors
    np.testing.assert_allclose(scaled, orig * 0.5, atol=1e-4)


def test_scale_audio_clips_at_1(tmp_path):
    src = _write_wav(tmp_path / "loud.wav")
    dst = tmp_path / "loud_scaled.wav"
    _scale_audio(src, dst, 10.0)  # extreme amplification should clip
    data, _ = sf.read(str(dst), dtype="float32")
    assert np.max(np.abs(data)) <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# Track2StemClient.health_check
# ---------------------------------------------------------------------------

def test_track2stem_health_check_ok():
    client = Track2StemClient("http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("requests.get", return_value=mock_resp):
        assert client.health_check() is True


def test_track2stem_health_check_fail():
    client = Track2StemClient("http://localhost:8080")
    with patch("requests.get", side_effect=ConnectionError("refused")):
        assert client.health_check() is False


def test_track2stem_health_check_non_200():
    client = Track2StemClient("http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("requests.get", return_value=mock_resp):
        assert client.health_check() is False
