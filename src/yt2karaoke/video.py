"""Render synchronized karaoke MP4s and separate original-vocal mixes."""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .transcriber import LyricLine
from .visuals import render_lyric_frame


class VideoError(Exception):
    """Raised when audio inspection or video encoding fails."""


def validate_vocals_volume(value: float) -> float:
    """Validate the shared 0-to-1 vocal gain used by the API and renderers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("vocals_volume must be a number between 0 and 1.")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("vocals_volume must be a finite number between 0 and 1.")
    return float(value)


def _audio_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
    except FileNotFoundError as exc:
        raise VideoError("ffprobe was not found. Install ffmpeg, which includes ffprobe.") from exc
    if result.returncode != 0:
        raise VideoError(f"Could not read instrumental audio: {result.stderr.strip()}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise VideoError("Could not determine the instrumental audio duration.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise VideoError("Instrumental audio duration must be finite and greater than zero.")
    return duration


def _mix_filter(volume: float) -> str:
    return (
        f"[2:a]volume={volume}[voice];"
        "[1:a][voice]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.98:level=false:latency=true[mix]"
    )


def build_video(
    instrumental_path: str | os.PathLike,
    lyrics: list[LyricLine],
    output_path: str | os.PathLike,
    *,
    width: int = 1280,
    height: int = 720,
    fps: float = 24.0,
    visual_style: str = "plasma",
    visual_speed: float = 0.5,
    font_size: int = 52,
    vocals_path: Optional[str | os.PathLike] = None,
    vocals_volume: float = 0.0,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Path:
    """Pipe NumPy/Pillow lyric frames into FFmpeg with H.264/AAC audio.

    Full-strength vocals are optional and receive ``vocals_volume`` exactly
    once. The existing destination is replaced only after successful encoding.
    """
    volume = validate_vocals_volume(vocals_volume)
    if volume > 0 and not vocals_path:
        raise VideoError("Provide vocals_path when adding original vocals.")
    if width <= 0 or height <= 0 or width % 2 or height % 2 or not math.isfinite(fps) or fps <= 0:
        raise VideoError("Video dimensions must be positive even numbers and fps must be positive.")
    if visual_style not in ("plasma", "gradient"):
        raise VideoError("Choose plasma or gradient for the video background.")
    if font_size <= 0:
        raise VideoError("The lyric font size must be positive.")
    instrumental_path, output_path = Path(instrumental_path), Path(output_path)
    duration = _audio_duration(instrumental_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_gen = _FrameGenerator(
        lyrics, duration, fps, width, height, visual_style, visual_speed, font_size,
    )
    frame_count = math.ceil(duration * fps)
    with tempfile.NamedTemporaryFile(suffix=".mp4", prefix=".render_", dir=output_path.parent) as handle:
        temporary = Path(handle.name)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
        "-framerate", f"{fps:g}", "-i", "pipe:0", "-i", str(instrumental_path),
    ]
    if vocals_path and volume > 0:
        command.extend(["-i", str(vocals_path), "-filter_complex", _mix_filter(volume)])
    command.extend([
        "-map", "0:v:0", "-map", "[mix]" if volume > 0 else "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-threads", "2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{duration:.9f}", "-shortest", "-movflags", "+faststart", str(temporary),
    ])
    process = None
    try:
        with tempfile.TemporaryFile() as errors:
            try:
                try:
                    process = subprocess.Popen(
                        command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                        stderr=errors, bufsize=0,
                    )
                except FileNotFoundError as exc:
                    raise VideoError("ffmpeg was not found. Install ffmpeg and add it to PATH.") from exc
                if process.stdin is None:
                    raise VideoError("Could not open the FFmpeg frame input.")
                if on_progress:
                    on_progress(0.0)
                try:
                    for index in range(frame_count):
                        frame = frame_gen.make_frame(index / fps)
                        if frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                            raise VideoError("The renderer produced an invalid RGB video frame.")
                        remaining = memoryview(frame).cast("B")
                        while remaining:
                            written = process.stdin.write(remaining)
                            if written is None or written <= 0:
                                raise BrokenPipeError("FFmpeg stopped accepting video frames.")
                            remaining = remaining[written:]
                        if on_progress:
                            on_progress((index + 1) / frame_count)
                    process.stdin.close()
                    returncode = process.wait()
                except BrokenPipeError as exc:
                    process.wait()
                    errors.seek(0)
                    detail = errors.read().decode("utf-8", errors="replace").strip()
                    raise VideoError(f"FFmpeg stopped encoding: {detail or str(exc)}") from exc
                if returncode != 0:
                    errors.seek(0)
                    detail = errors.read().decode("utf-8", errors="replace").strip()
                    raise VideoError(f"FFmpeg encoding failed (exit {returncode}): {detail}")
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    if process.stdin is not None and not process.stdin.closed:
                        process.stdin.close()
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def remix_video(
    video_path: str | os.PathLike,
    instrumental_path: str | os.PathLike,
    vocals_path: str | os.PathLike,
    output_path: str | os.PathLike,
    vocals_volume: float,
) -> Path:
    """Create a separate vocal mix, copying the synchronized video unchanged."""
    volume = validate_vocals_volume(vocals_volume)
    video_path, output_path = Path(video_path), Path(output_path)
    if video_path.resolve() == output_path.resolve():
        raise VideoError("A vocal mix must not overwrite the instrumental video.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".mp4", prefix=".mix_", dir=output_path.parent) as handle:
        temporary = Path(handle.name)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(video_path), "-i", str(instrumental_path), "-i", str(vocals_path),
        "-filter_complex", _mix_filter(volume), "-map", "0:v:0", "-map", "[mix]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(temporary),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise VideoError(f"Could not create vocal mix: {result.stderr.strip()}")
        temporary.replace(output_path)
    except FileNotFoundError as exc:
        raise VideoError("ffmpeg was not found. Install ffmpeg and make it available in PATH.") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


class _FrameGenerator:
    """Stateful frame generator sharing precomputed background coordinates."""

    def __init__(
        self,
        lyrics: list[LyricLine],
        duration: float,
        fps: float,
        width: int,
        height: int,
        visual_style: str,
        visual_speed: float,
        font_size: int,
    ) -> None:
        self.lyrics = lyrics
        self.duration = duration
        self.fps = fps
        self.width = width
        self.height = height
        self.visual_style = visual_style
        self.visual_speed = visual_speed
        self.font_size = font_size
        xs = np.linspace(0, 2 * math.pi, width, dtype=np.float32)
        ys = np.linspace(0, 2 * math.pi, height, dtype=np.float32)
        self._xg, self._yg = np.meshgrid(xs, ys)

    def make_frame(self, t: float) -> np.ndarray:
        """Return the composited RGB frame for a time in seconds."""
        from .visuals import _render_plasma_numpy, _render_gradient_numpy

        scaled_t = t * self.visual_speed
        if self.visual_style == "plasma":
            bg = _render_plasma_numpy(self._xg, self._yg, scaled_t, self.width, self.height)
        else:
            bg = _render_gradient_numpy(self._xg, self._yg, scaled_t, self.width, self.height)
        current_line: Optional[LyricLine] = None
        next_line: Optional[LyricLine] = None
        current_word = ""
        current_word_index: Optional[int] = None
        for index, line in enumerate(self.lyrics):
            if line.start <= t < line.end:
                current_line = line
                for word_index, word in enumerate(line.words):
                    if word.start <= t < word.end:
                        current_word = word.word
                        current_word_index = word_index
                        break
                if index + 1 < len(self.lyrics):
                    next_line = self.lyrics[index + 1]
                break
        return render_lyric_frame(
            bg, current_line.text if current_line else "",
            next_line.text if next_line else "", current_word,
            width=self.width, height=self.height, font_size=self.font_size,
            highlight_index=current_word_index,
        )
