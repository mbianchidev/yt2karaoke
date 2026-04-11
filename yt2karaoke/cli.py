"""Command-line interface for yt2karaoke."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Optional

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="yt2karaoke")
def main() -> None:
    """yt2karaoke — Turn any YouTube link into a karaoke experience."""


# ---------------------------------------------------------------------------
# convert command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("url")
@click.option("-o", "--output-dir", default=".", show_default=True, help="Output directory.")
@click.option("--filename", default=None, help="Output filename stem (no extension).")
@click.option(
    "--vocals-volume",
    default=0.0,
    show_default=True,
    type=float,
    help="Volume of original vocals in the mix (0=muted, 1=full).",
)
@click.option(
    "--whisper-model",
    default="base",
    show_default=True,
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    help="Whisper model size for lyric transcription.",
)
@click.option(
    "--separation-model",
    default="htdemucs",
    show_default=True,
    help="Demucs model for stem separation.",
)
@click.option(
    "--track2stem-url",
    default=None,
    help="URL of a running track2stem service (e.g. http://localhost:8080).",
)
@click.option(
    "--visual-style",
    default="plasma",
    show_default=True,
    type=click.Choice(["plasma", "gradient"]),
    help="Background visual style.",
)
@click.option(
    "--visual-speed",
    default=0.5,
    show_default=True,
    type=float,
    help="Animation speed (lower = slower / more trippy).",
)
@click.option("--width", default=1280, show_default=True, type=int, help="Video width.")
@click.option("--height", default=720, show_default=True, type=int, help="Video height.")
@click.option("--fps", default=24.0, show_default=True, type=float, help="Video frame rate.")
@click.option("--language", default=None, help="Language code for transcription (auto-detect if omitted).")
@click.option("--reverb/--no-reverb", default=True, show_default=True, help="Apply reverb to vocals.")
@click.option("--delay/--no-delay", default=True, show_default=True, help="Apply delay/echo to vocals.")
@click.option("--distortion/--no-distortion", default=False, show_default=True, help="Apply distortion to vocals.")
def convert(
    url: str,
    output_dir: str,
    filename: Optional[str],
    vocals_volume: float,
    whisper_model: str,
    separation_model: str,
    track2stem_url: Optional[str],
    visual_style: str,
    visual_speed: float,
    width: int,
    height: int,
    fps: float,
    language: Optional[str],
    reverb: bool,
    delay: bool,
    distortion: bool,
) -> None:
    """Convert a YouTube URL to a karaoke video.

    \b
    URL   YouTube video URL (e.g. https://youtube.com/watch?v=xxx)

    \b
    Example:
        yt2karaoke convert "https://youtube.com/watch?v=dQw4w9WgXcQ" -o ./output
    """
    from .pipeline import KaraokeConfig, run

    config = KaraokeConfig(
        youtube_url=url,
        output_dir=output_dir,
        output_filename=filename,
        vocals_volume=vocals_volume,
        whisper_model=whisper_model,
        separation_model=separation_model,
        track2stem_url=track2stem_url,
        visual_style=visual_style,
        visual_speed=visual_speed,
        video_width=width,
        video_height=height,
        fps=fps,
        language=language,
        apply_reverb=reverb,
        apply_delay=delay,
        apply_distortion=distortion,
    )

    click.echo(f"🎤 yt2karaoke v{__version__}")
    click.echo(f"   URL: {url}")
    click.echo(f"   Output: {output_dir}")

    try:
        result = run(config)
        click.echo(click.style("\n✅ Done!", fg="green", bold=True))
        click.echo(f"   Video:        {result.video_path}")
        click.echo(f"   Instrumental: {result.instrumental_path}")
        click.echo(f"   Lyrics (LRC): {result.lyrics_lrc_path}")
        click.echo(f"   Lyrics (ASS): {result.lyrics_ass_path}")
    except KeyboardInterrupt:
        click.echo("\nAborted.", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(click.style(f"\n❌ Error: {exc}", fg="red"), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# player command
# ---------------------------------------------------------------------------

@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind the player to.")
@click.option("--port", default=5000, show_default=True, type=int, help="Port for the player web server.")
@click.option("-o", "--output-dir", default="karaoke_output", show_default=True, help="Directory for karaoke files.")
@click.option(
    "--whisper-model",
    default="base",
    show_default=True,
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    help="Whisper model for transcription.",
)
@click.option(
    "--separation-model",
    default="htdemucs",
    show_default=True,
    help="Demucs model for stem separation.",
)
@click.option(
    "--track2stem-url",
    default=None,
    help="URL of a running track2stem service.",
)
@click.option(
    "--vocals-volume",
    default=0.0,
    show_default=True,
    type=float,
    help="Volume of original vocals in the mix.",
)
@click.option(
    "--visual-style",
    default="plasma",
    show_default=True,
    type=click.Choice(["plasma", "gradient"]),
    help="Background visual style.",
)
@click.option("--debug", is_flag=True, default=False, help="Enable Flask debug mode.")
def player(
    host: str,
    port: int,
    output_dir: str,
    whisper_model: str,
    separation_model: str,
    track2stem_url: Optional[str],
    vocals_volume: float,
    visual_style: str,
    debug: bool,
) -> None:
    """Start the yt2karaoke web player.

    Open http://HOST:PORT in your browser to access the player.

    \b
    Example:
        yt2karaoke player --port 5000 --output-dir ./karaoke_output
    """
    from .player.app import create_app

    app, socketio = create_app(
        output_dir=output_dir,
        whisper_model=whisper_model,
        separation_model=separation_model,
        track2stem_url=track2stem_url,
        vocals_volume=vocals_volume,
        visual_style=visual_style,
    )

    click.echo(f"🎤 yt2karaoke player")
    click.echo(f"   Open: http://{host}:{port}")
    click.echo(f"   Press Ctrl+C to stop.\n")

    socketio.run(app, host=host, port=port, debug=debug)
