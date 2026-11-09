"""Download audio from YouTube using yt-dlp."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yt_dlp


class DownloadError(Exception):
    """Raised when a YouTube download fails."""


def _ydl_options() -> dict[str, object]:
    return {
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }


def download_audio(
    url: str,
    output_dir: str | os.PathLike = ".",
    filename: Optional[str] = None,
    audio_format: str = "wav",
) -> Path:
    """Download audio from a YouTube URL.

    Args:
        url: YouTube video URL.
        output_dir: Directory to save the downloaded audio.
        filename: Output filename without extension.  Defaults to the video title.
        audio_format: Audio format (wav, mp3, flac).  Defaults to "wav".

    Returns:
        Path to the downloaded audio file.

    Raises:
        DownloadError: If the download or extraction fails.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(output_dir / (filename if filename else "%(title)s")) + ".%(ext)s"

    ydl_opts = _ydl_options()
    ydl_opts.update({
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "0",  # lossless for WAV/FLAC
            }
        ],
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "unknown")
            safe_title = yt_dlp.utils.sanitize_filename(title)
            stem = filename if filename else safe_title
            audio_path = output_dir / f"{stem}.{audio_format}"
            return audio_path
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(str(exc)) from exc


def get_video_info(url: str) -> dict:
    """Return metadata for a YouTube video without downloading it.

    Args:
        url: YouTube video URL.

    Returns:
        Dictionary containing video metadata (title, duration, thumbnail, …).

    Raises:
        DownloadError: If metadata extraction fails.
    """
    ydl_opts = _ydl_options()
    ydl_opts["skip_download"] = True
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
                "url": url,
            }
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(str(exc)) from exc
