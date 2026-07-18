"""Audio stem separation — vocals + instrumental.

Uses Demucs (the same AI model powering @mbianchidev/track2stem) directly as a
Python library.  An optional REST client is also provided so you can delegate
processing to a running track2stem service when available.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf


class SeparationError(Exception):
    """Raised when audio separation fails."""


# ---------------------------------------------------------------------------
# Demucs-based separator (direct dependency — same core as track2stem)
# ---------------------------------------------------------------------------


def separate(
    audio_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    model: str = "htdemucs",
    vocals_volume: float = 1.0,
) -> dict[str, Path]:
    """Separate *audio_path* into vocals and instrumental stems.

    Args:
        audio_path: Path to the source audio file.
        output_dir: Directory where stem files will be written.
        model: Demucs model name.  ``"htdemucs"`` gives vocals + drums + bass +
            other (4-stem).  Only the vocals and instrumental (everything else
            mixed together) are returned.
        vocals_volume: Scalar to apply to the vocals track (0 = muted, 1 =
            original level).  Values > 1 amplify the vocals.

    Returns:
        Dictionary with ``"vocals"`` and ``"instrumental"`` keys, each pointing
        to the corresponding WAV file.

    Raises:
        SeparationError: If Demucs is not installed or the separation fails.
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _run_demucs(audio_path, output_dir, model)

    stems_dir = _find_stems_dir(output_dir, model, audio_path.stem)
    vocal_path = _find_stem_file(stems_dir, "vocals")
    other_stems = [p for p in stems_dir.iterdir() if p.stem != "vocals"]

    # Mix non-vocal stems into a single instrumental track
    instrumental_path = output_dir / f"{audio_path.stem}_instrumental.wav"
    _mix_stems(other_stems, instrumental_path)

    # Apply vocals volume scaling
    if vocals_volume != 1.0:
        vocals_out = output_dir / f"{audio_path.stem}_vocals.wav"
        _scale_audio(vocal_path, vocals_out, vocals_volume)
        vocal_path = vocals_out

    return {
        "vocals": vocal_path,
        "instrumental": instrumental_path,
    }


def _run_demucs(
    audio_path: Path, output_dir: Path, model: str
) -> None:
    """Invoke the ``demucs`` CLI to separate *audio_path*."""
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=vocals",
        f"--out={output_dir}",
        f"--name={model}",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SeparationError(
            f"Demucs failed (exit {result.returncode}):\n{result.stderr}"
        )


def _find_stems_dir(output_dir: Path, model: str, stem_name: str) -> Path:
    """Locate the directory that Demucs wrote separated stems into."""
    # Demucs writes to: <output_dir>/<model>/<track_stem>/
    candidate = output_dir / model / stem_name
    if candidate.is_dir():
        return candidate
    # Fallback: search recursively
    for path in output_dir.rglob(stem_name):
        if path.is_dir():
            return path
    raise SeparationError(
        f"Could not find stems directory for '{stem_name}' inside '{output_dir}'"
    )


def _find_stem_file(stems_dir: Path, stem_name: str) -> Path:
    """Return the file for *stem_name* inside *stems_dir*."""
    for ext in ("wav", "mp3", "flac"):
        candidate = stems_dir / f"{stem_name}.{ext}"
        if candidate.exists():
            return candidate
    raise SeparationError(
        f"Could not find '{stem_name}' stem in '{stems_dir}'"
    )


def _mix_stems(stem_paths: list[Path], output_path: Path) -> None:
    """Mix multiple audio files into one by summing samples."""
    if not stem_paths:
        raise SeparationError("No stems to mix.")

    mixed: Optional[np.ndarray] = None
    sample_rate: Optional[int] = None

    for stem in stem_paths:
        data, sr = sf.read(str(stem), always_2d=True, dtype="float32")
        if mixed is None:
            mixed = data.copy()
            sample_rate = sr
        else:
            # Match length
            min_len = min(len(mixed), len(data))
            mixed = mixed[:min_len] + data[:min_len]

    # Normalize to prevent clipping
    max_val = np.max(np.abs(mixed))
    if max_val > 1.0:
        mixed /= max_val

    sf.write(str(output_path), mixed, sample_rate)


def _scale_audio(input_path: Path, output_path: Path, factor: float) -> None:
    """Write *input_path* scaled by *factor* to *output_path*."""
    data, sr = sf.read(str(input_path), always_2d=True, dtype="float32")
    data = np.clip(data * factor, -1.0, 1.0)
    sf.write(str(output_path), data, sr)


# ---------------------------------------------------------------------------
# Optional: track2stem REST client
# ---------------------------------------------------------------------------


class Track2StemClient:
    """REST client for a running @mbianchidev/track2stem service.

    Use this when you prefer to offload the heavy Demucs processing to the
    Docker-based track2stem service instead of running it in-process.

    Example::

        client = Track2StemClient("http://localhost:8080")
        stems = client.separate(audio_path, output_dir)
    """

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url.rstrip("/")

    def health_check(self) -> bool:
        """Return *True* if the track2stem service is reachable."""
        import requests  # local import — optional dependency in this context

        try:
            resp = requests.get(f"{self.base_url}/api/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def separate(
        self,
        audio_path: str | os.PathLike,
        output_dir: str | os.PathLike,
        vocals_volume: float = 1.0,
    ) -> dict[str, Path]:
        """Upload *audio_path* to track2stem and download the separated stems.

        Args:
            audio_path: Path to the audio file to separate.
            output_dir: Directory to save the downloaded stems.
            vocals_volume: Volume scaling for the vocals track.

        Returns:
            Dictionary with ``"vocals"`` and ``"instrumental"`` keys.

        Raises:
            SeparationError: If the request fails or the service is unavailable.
        """
        import requests
        import time

        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Upload file
        with open(audio_path, "rb") as fh:
            resp = requests.post(
                f"{self.base_url}/api/upload",
                files={"file": (audio_path.name, fh, "audio/wav")},
                data={"stem_mode": "isolate", "isolate_stem": "vocals"},
                timeout=30,
            )
        if resp.status_code not in (200, 201):
            raise SeparationError(
                f"track2stem upload failed ({resp.status_code}): {resp.text}"
            )

        job_id = resp.json()["id"]

        # Poll for completion
        for _ in range(360):  # up to 6 minutes
            status_resp = requests.get(
                f"{self.base_url}/api/jobs/{job_id}", timeout=10
            )
            status = status_resp.json().get("status", "")
            if status == "completed":
                break
            if status == "failed":
                raise SeparationError("track2stem job failed.")
            time.sleep(1)
        else:
            raise SeparationError("track2stem job timed out.")

        # Download vocals
        vocals_path = output_dir / f"{audio_path.stem}_vocals.wav"
        self._download_stem(job_id, "vocals", vocals_path)

        # Download instrumental (no_vocals in isolate mode)
        instrumental_path = output_dir / f"{audio_path.stem}_instrumental.wav"
        self._download_stem(job_id, "no_vocals", instrumental_path)

        # Apply vocals volume
        if vocals_volume != 1.0:
            _scale_audio(vocals_path, vocals_path, vocals_volume)

        return {"vocals": vocals_path, "instrumental": instrumental_path}

    def _download_stem(self, job_id: str, stem: str, dest: Path) -> None:
        import requests

        resp = requests.get(
            f"{self.base_url}/api/download/{job_id}/{stem}", timeout=120
        )
        if resp.status_code != 200:
            raise SeparationError(
                f"Failed to download stem '{stem}' ({resp.status_code})"
            )
        dest.write_bytes(resp.content)
