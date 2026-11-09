"""Trippy, colorful, slow-moving background visuals for karaoke.

Generates animated background frames using NumPy and Pillow.  The visuals
are designed to be mild (not overwhelming) while being vibrant and
psychedelic — flowing gradients, color cycles, plasma waves, and slow
particle drift.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Generator, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------

def generate_frames(
    duration: float,
    fps: float = 24.0,
    width: int = 1280,
    height: int = 720,
    speed: float = 0.5,
    style: str = "plasma",
) -> Generator[np.ndarray, None, None]:
    """Yield background video frames as NumPy arrays (H x W x 3, uint8).

    Args:
        duration: Total duration in seconds.
        fps: Frames per second.
        width: Frame width in pixels.
        height: Frame height in pixels.
        speed: Animation speed multiplier (lower = slower / more trippy).
        style: Visual style — ``"plasma"`` or ``"gradient"``.

    Yields:
        NumPy arrays of shape ``(height, width, 3)`` with dtype ``uint8``.
    """
    total_frames = int(duration * fps)
    dt = speed / fps  # time step per frame

    # Pre-compute normalized coordinate grids
    xs = np.linspace(0, 2 * math.pi, width, dtype=np.float32)
    ys = np.linspace(0, 2 * math.pi, height, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)

    t = 0.0
    for _ in range(total_frames):
        if style == "plasma":
            frame = _render_plasma_numpy(xg, yg, t, width, height)
        else:
            frame = _render_gradient_numpy(xg, yg, t, width, height)
        yield frame
        t += dt


def _render_plasma_numpy(
    xg: np.ndarray, yg: np.ndarray, t: float, width: int, height: int
) -> np.ndarray:
    """Render a plasma effect using vectorised NumPy operations."""
    v = (
        np.sin(xg * 1.5 + t)
        + np.sin(yg * 1.5 + t * 0.7)
        + np.sin((xg + yg) * 1.0 + t * 0.5)
        + np.sin(np.sqrt(xg ** 2 + yg ** 2 + 0.5) * 1.5 - t)
    )
    v = (v + 4.0) / 8.0  # → 0..1

    # Map value to HSV hue cycle
    hue = (v + t * 0.03) % 1.0  # type: ignore[operator]
    saturation = np.full_like(v, 0.85)
    value_channel = np.full_like(v, 0.85)

    # Vectorised HSV→RGB conversion
    i = (hue * 6.0).astype(np.int32)
    f = hue * 6.0 - i
    p = value_channel * (1.0 - saturation)
    q = value_channel * (1.0 - f * saturation)
    tk = value_channel * (1.0 - (1.0 - f) * saturation)

    rgb = np.zeros((height, width, 3), dtype=np.float32)
    for cond, (r_, g_, b_) in [
        (i == 0, (value_channel, tk, p)),
        (i == 1, (q, value_channel, p)),
        (i == 2, (p, value_channel, tk)),
        (i == 3, (p, q, value_channel)),
        (i == 4, (tk, p, value_channel)),
        (i == 5, (value_channel, p, q)),
    ]:
        mask = cond
        rgb[:, :, 0][mask] = r_[mask]
        rgb[:, :, 1][mask] = g_[mask]
        rgb[:, :, 2][mask] = b_[mask]

    return (rgb * 255).clip(0, 255).astype(np.uint8)


def _render_gradient_numpy(
    xg: np.ndarray, yg: np.ndarray, t: float, width: int, height: int
) -> np.ndarray:
    """Render a slow-moving colour gradient."""
    r = ((np.sin(xg * 0.5 + t) + 1.0) / 2.0 * 200 + 55).astype(np.uint8)
    g = ((np.sin(yg * 0.5 + t * 0.8 + 2.0) + 1.0) / 2.0 * 200 + 55).astype(np.uint8)
    b = ((np.sin((xg + yg) * 0.3 + t * 0.6 + 4.0) + 1.0) / 2.0 * 200 + 55).astype(
        np.uint8
    )
    return np.stack([r, g, b], axis=-1)


# ---------------------------------------------------------------------------
# Overlay helpers
# ---------------------------------------------------------------------------

def render_lyric_frame(
    background: np.ndarray,
    current_line: str,
    next_line: str = "",
    highlight_word: str = "",
    width: int = 1280,
    height: int = 720,
    font_size: int = 52,
    highlight_index: Optional[int] = None,
) -> np.ndarray:
    """Overlay karaoke lyrics on a background frame.

    The *current_line* is displayed in bright white; the highlighted word is
    shown in vivid yellow.  The *next_line* is shown dimmed below.

    Args:
        background: Background frame as NumPy array (H x W x 3).
        current_line: Currently active lyric line.
        next_line: Next lyric line (shown dimmed below).
        highlight_word: Word within *current_line* currently being sung.
        width: Ignored — dimensions are derived from *background* shape.
        height: Ignored — dimensions are derived from *background* shape.
        font_size: Font size for the main lyrics.

    Returns:
        Composited frame as NumPy array (H x W x 3, uint8).
    """
    # Always derive dimensions from the actual background to ensure correct placement
    height, width = background.shape[:2]

    bg = Image.fromarray(background)
    # Darken the background slightly so text is readable
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 100))
    bg = bg.convert("RGBA")
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)

    font = _load_font(font_size, True)
    small_font = _load_font(max(1, int(font_size * 0.7)), False)

    # Draw current line with word highlighting
    _draw_line_with_highlight(
        draw, current_line, highlight_word, font, width, height,
        y_frac=0.68, highlight_index=highlight_index,
    )

    # Draw next line dimmed
    if next_line:
        _draw_centered_text(draw, next_line, small_font, width, height, y_frac=0.85, color=(180, 180, 180))

    return np.array(bg.convert("RGB"), dtype=np.uint8)


@lru_cache(maxsize=128)
def _load_font(size: int, bold: bool):
    bundled = Path(__file__).parent / "player" / "static" / "fonts" / "outfit.ttf"
    candidates = [
        str(bundled),
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        f"C:/Windows/Fonts/{'arialbd' if bold else 'arial'}.ttf",
    ]
    for candidate in candidates:
        try:
            font = ImageFont.truetype(candidate, size)
            if candidate == str(bundled):
                font.set_variation_by_axes([650 if bold else 450])
            return font
        except (OSError, ValueError):
            continue
    return ImageFont.load_default(size=size)


def _wrap_words(draw, words: list[str], font, max_width: float):
    rows = []
    row = []
    row_width = 0.0
    space_width = draw.textlength(" ", font=font)
    for index, word in enumerate(words):
        word_width = draw.textlength(word, font=font)
        if row and row_width + space_width + word_width > max_width:
            rows.append((row, row_width))
            row, row_width = [], 0.0
        if row:
            row_width += space_width
        row.append((index, word, word_width))
        row_width += word_width
    if row:
        rows.append((row, row_width))
    return rows, space_width


def _draw_line_with_highlight(
    draw: ImageDraw.ImageDraw,
    line: str,
    highlight_word: str,
    font,
    width: int,
    height: int,
    y_frac: float = 0.72,
    highlight_index: Optional[int] = None,
) -> None:
    """Draw a lyric line; the highlighted word appears in yellow."""
    words = line.split()
    if not words:
        return

    size = font.size
    rows, space_width = _wrap_words(draw, words, font, width * 0.88)
    while size > 1 and (len(rows) * size * 1.25 > height * 0.38 or any(w > width * 0.88 for _, w in rows)):
        size -= 1
        font = _load_font(size, True)
        rows, space_width = _wrap_words(draw, words, font, width * 0.88)
    line_height = size * 1.25
    y = height * y_frac - (len(rows) - 1) * line_height / 2
    for row, row_width in rows:
        x = (width - row_width) / 2
        for index, word, word_width in row:
            highlighted = index == highlight_index if highlight_index is not None else (
                bool(highlight_word)
                and word.strip(".,!?\"'").lower() == highlight_word.strip(".,!?\"'").lower()
            )
            color = (255, 255, 0) if highlighted else (255, 255, 255)
            draw.text((x, y), word, font=font, fill=color,
                      stroke_width=max(1, size // 26), stroke_fill=(0, 0, 0))
            x += word_width + space_width
        y += line_height


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    width: int,
    height: int,
    y_frac: float = 0.85,
    color: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Draw text centred horizontally at a fractional vertical position."""
    size = font.size
    while size > 1 and draw.textlength(text, font=font) > width * 0.88:
        size -= 1
        font = _load_font(size, False)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    y = int(height * y_frac)
    draw.text((x, y), text, font=font, fill=color, stroke_width=1, stroke_fill=(0, 0, 0))
