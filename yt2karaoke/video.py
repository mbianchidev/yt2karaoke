"""Assemble the final karaoke video.

Combines:
- Instrumental audio track
- Trippy animated background visuals
- Karaoke-style lyrics overlay (word-by-word highlighting)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from .transcriber import LyricLine, LyricWord
from .visuals import generate_frames, render_lyric_frame


class VideoError(Exception):
    """Raised when video assembly fails."""


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
) -> Path:
    """Build the karaoke video.

    Args:
        instrumental_path: Path to the instrumental audio file.
        lyrics: List of :class:`~yt2karaoke.transcriber.LyricLine` objects.
        output_path: Destination path for the output video (MP4).
        width: Video width in pixels.
        height: Video height in pixels.
        fps: Output frame rate.
        visual_style: Background visual style — ``"plasma"`` or ``"gradient"``.
        visual_speed: Animation speed (lower = slower / more trippy).
        font_size: Font size for lyrics.
        vocals_path: Optional path to processed vocals to mix into output.
        vocals_volume: Volume of the vocals in the final mix (0 = muted).

    Returns:
        Path to the output video file.

    Raises:
        VideoError: If moviepy is not installed or video assembly fails.
    """
    try:
        from moviepy.editor import (
            VideoClip,
            AudioFileClip,
            CompositeAudioClip,
            concatenate_audioclips,
        )
        from moviepy.audio.AudioClip import AudioArrayClip
    except ImportError as exc:
        raise VideoError(
            "moviepy is not installed.  Run: pip install moviepy"
        ) from exc

    instrumental_path = Path(instrumental_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine video duration from the instrumental audio
    instrumental_clip = AudioFileClip(str(instrumental_path))
    duration = instrumental_clip.duration

    # Build frame generator state
    frame_gen = _FrameGenerator(
        lyrics=lyrics,
        duration=duration,
        fps=fps,
        width=width,
        height=height,
        visual_style=visual_style,
        visual_speed=visual_speed,
        font_size=font_size,
    )

    # Create video clip using MoviePy's make_frame callback
    video_clip = VideoClip(frame_gen.make_frame, duration=duration)
    video_clip = video_clip.set_fps(fps)

    # Build audio: instrumental + optional vocals mix
    audio_tracks = [instrumental_clip]
    if vocals_path and vocals_volume > 0:
        try:
            vocals_clip = AudioFileClip(str(vocals_path)).volumex(vocals_volume)
            audio_tracks.append(vocals_clip)
        except Exception:
            pass  # If vocals fail to load, just use instrumental

    if len(audio_tracks) > 1:
        audio = CompositeAudioClip(audio_tracks)
    else:
        audio = audio_tracks[0]

    video_clip = video_clip.set_audio(audio)

    # Write output
    try:
        video_clip.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=2,
            logger=None,
        )
    except Exception as exc:
        raise VideoError(f"Failed to write video: {exc}") from exc
    finally:
        instrumental_clip.close()
        video_clip.close()

    return output_path


class _FrameGenerator:
    """Stateful frame generator used as MoviePy's ``make_frame`` callback."""

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

        import math
        # Pre-compute normalized coordinate grids once
        xs = np.linspace(0, 2 * math.pi, width, dtype=np.float32)
        ys = np.linspace(0, 2 * math.pi, height, dtype=np.float32)
        self._xg, self._yg = np.meshgrid(xs, ys)

    def make_frame(self, t: float) -> np.ndarray:
        """Return the composited frame (H x W x 3) for time *t* (seconds)."""
        from .visuals import _render_plasma_numpy, _render_gradient_numpy

        # Background
        scaled_t = t * self.visual_speed
        if self.visual_style == "plasma":
            bg = _render_plasma_numpy(self._xg, self._yg, scaled_t, self.width, self.height)
        else:
            bg = _render_gradient_numpy(self._xg, self._yg, scaled_t, self.width, self.height)

        # Find current and next lyric lines
        current_line: Optional[LyricLine] = None
        next_line: Optional[LyricLine] = None
        current_word: str = ""

        for i, line in enumerate(self.lyrics):
            if line.start <= t <= line.end:
                current_line = line
                # Find the word being sung at time t
                for word in line.words:
                    if word.start <= t <= word.end:
                        current_word = word.word
                        break
                if i + 1 < len(self.lyrics):
                    next_line = self.lyrics[i + 1]
                break

        current_text = current_line.text if current_line else ""
        next_text = next_line.text if next_line else ""

        return render_lyric_frame(
            bg,
            current_text,
            next_text,
            current_word,
            width=self.width,
            height=self.height,
            font_size=self.font_size,
        )
