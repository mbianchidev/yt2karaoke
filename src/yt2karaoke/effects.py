"""Audio effects for the vocals track.

Applies delay, reverb and distortion using the ``pedalboard`` library.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import soundfile as sf


class EffectsError(Exception):
    """Raised when applying audio effects fails."""


def apply_effects(
    vocals_path: str | os.PathLike,
    output_path: str | os.PathLike,
    *,
    reverb: bool = True,
    reverb_room_size: float = 0.4,
    reverb_wet_level: float = 0.25,
    delay: bool = True,
    delay_seconds: float = 0.3,
    delay_feedback: float = 0.3,
    delay_mix: float = 0.3,
    distortion: bool = False,
    distortion_drive_db: float = 10.0,
    chorus: bool = False,
    chorus_depth: float = 0.15,
) -> Path:
    """Apply audio effects to a vocals track.

    Args:
        vocals_path: Path to the input vocals audio file.
        output_path: Path for the processed output file.
        reverb: Enable reverb effect.
        reverb_room_size: Room size for reverb (0 – 1).
        reverb_wet_level: Wet/dry mix for reverb (0 – 1).
        delay: Enable delay (echo) effect.
        delay_seconds: Delay time in seconds.
        delay_feedback: Feedback amount for delay (0 – 1).
        delay_mix: Wet mix level for delay (0 – 1).
        distortion: Enable distortion effect.
        distortion_drive_db: Drive amount in dB for distortion.
        chorus: Enable chorus effect.
        chorus_depth: Depth of the chorus effect (0 – 1).

    Returns:
        Path to the processed audio file.

    Raises:
        EffectsError: If ``pedalboard`` is not installed or processing fails.
    """
    try:
        from pedalboard import (
            Pedalboard,
            Reverb,
            Delay,
            Distortion,
            Chorus,
        )
        from pedalboard.io import AudioFile
    except ImportError as exc:
        raise EffectsError(
            "pedalboard is not installed.  Run: pip install pedalboard"
        ) from exc

    vocals_path = Path(vocals_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    board_plugins = []
    if reverb:
        board_plugins.append(
            Reverb(room_size=reverb_room_size, wet_level=reverb_wet_level)
        )
    if delay:
        board_plugins.append(
            Delay(delay_seconds=delay_seconds, feedback=delay_feedback, mix=delay_mix)
        )
    if distortion:
        board_plugins.append(Distortion(drive_db=distortion_drive_db))
    if chorus:
        board_plugins.append(Chorus(depth=chorus_depth))

    if not board_plugins:
        # No effects requested — just copy the file
        import shutil
        shutil.copy2(vocals_path, output_path)
        return output_path

    board = Pedalboard(board_plugins)

    with AudioFile(str(vocals_path)) as source:
        sample_rate = source.samplerate
        with AudioFile(
            str(output_path),
            "w",
            samplerate=sample_rate,
            num_channels=source.num_channels,
        ) as dest:
            while source.tell() < source.frames:
                chunk = source.read(source.samplerate)  # 1-second chunks
                processed = board(chunk, sample_rate)
                dest.write(processed)

    return output_path


def _numpy_fallback_effects(
    data: np.ndarray,
    sample_rate: int,
    *,
    delay_seconds: float = 0.3,
    delay_feedback: float = 0.3,
    reverb_decay: float = 0.5,
) -> np.ndarray:
    """Pure-NumPy fallback effect chain (delay + basic reverb).

    This is used when ``pedalboard`` is unavailable.  Quality is lower than
    the pedalboard implementation.

    Args:
        data: Audio samples shaped (frames, channels).
        sample_rate: Sample rate in Hz.
        delay_seconds: Echo delay time in seconds.
        delay_feedback: Echo decay factor (0 – 1).
        reverb_decay: Simple comb-filter reverb decay (0 – 1).

    Returns:
        Processed audio samples.
    """
    result = data.copy().astype(np.float32)
    delay_samples = int(delay_seconds * sample_rate)

    # Simple delay / echo
    for i in range(delay_samples, len(result)):
        result[i] += result[i - delay_samples] * delay_feedback

    # Very simple comb-filter reverb
    reverb_delay = int(0.05 * sample_rate)
    for i in range(reverb_delay, len(result)):
        result[i] += result[i - reverb_delay] * reverb_decay * 0.3

    # Normalize
    max_val = np.max(np.abs(result))
    if max_val > 1.0:
        result /= max_val

    return result


def apply_effects_numpy(
    vocals_path: str | os.PathLike,
    output_path: str | os.PathLike,
    *,
    delay_seconds: float = 0.3,
    delay_feedback: float = 0.3,
    reverb_decay: float = 0.5,
) -> Path:
    """Apply effects using the pure-NumPy fallback (no pedalboard required).

    Args:
        vocals_path: Path to the input vocals audio file.
        output_path: Path for the processed output file.
        delay_seconds: Echo delay time in seconds.
        delay_feedback: Echo decay factor.
        reverb_decay: Simple reverb decay factor.

    Returns:
        Path to the processed audio file.
    """
    vocals_path = Path(vocals_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data, sr = sf.read(str(vocals_path), always_2d=True, dtype="float32")
    processed = _numpy_fallback_effects(
        data,
        sr,
        delay_seconds=delay_seconds,
        delay_feedback=delay_feedback,
        reverb_decay=reverb_decay,
    )
    sf.write(str(output_path), processed, sr)
    return output_path
