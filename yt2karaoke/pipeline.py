"""Main pipeline: orchestrates the full YouTube → karaoke conversion."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class KaraokeConfig:
    """Configuration for a single karaoke processing job."""

    # Input
    youtube_url: str

    # Output
    output_dir: str | os.PathLike = "."
    output_filename: Optional[str] = None

    # Stem separation
    separation_model: str = "htdemucs"
    vocals_volume: float = 0.0  # 0 = muted originals, 1 = full originals

    # Transcription
    whisper_model: str = "base"
    language: Optional[str] = None

    # Audio effects on vocals (only applied when vocals_volume > 0)
    apply_reverb: bool = True
    apply_delay: bool = True
    apply_distortion: bool = False
    apply_chorus: bool = False

    # Video
    video_width: int = 1280
    video_height: int = 720
    fps: float = 24.0
    visual_style: str = "plasma"   # "plasma" or "gradient"
    visual_speed: float = 0.5
    font_size: int = 52

    # track2stem REST client (optional — set to use remote separation)
    track2stem_url: Optional[str] = None

    # Intermediate files directory (defaults to a temp dir inside output_dir)
    work_dir: Optional[str | os.PathLike] = None


@dataclass
class KaraokeResult:
    """Paths to the output artefacts from a completed pipeline run."""

    video_path: Path
    instrumental_path: Path
    vocals_path: Path
    lyrics_lrc_path: Optional[Path] = None
    lyrics_ass_path: Optional[Path] = None


def run(config: KaraokeConfig) -> KaraokeResult:
    """Execute the full yt2karaoke pipeline.

    Steps
    -----
    1. Download audio from YouTube.
    2. Separate into vocals + instrumental (via Demucs or track2stem API).
    3. Transcribe vocals to time-stamped lyrics (Whisper).
    4. Optionally apply audio effects to vocals.
    5. Generate karaoke video with animated background and synced lyrics.

    Args:
        config: :class:`KaraokeConfig` instance describing the job.

    Returns:
        :class:`KaraokeResult` with paths to all output files.
    """
    import tempfile
    from tqdm import tqdm

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up work directory for intermediate files
    if config.work_dir:
        work_dir = Path(config.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_work_dir = False
    else:
        _tmp = tempfile.mkdtemp(dir=output_dir, prefix=".yt2karaoke_work_")
        work_dir = Path(_tmp)
        _cleanup_work_dir = True

    steps = [
        "Downloading audio",
        "Separating stems",
        "Transcribing lyrics",
        "Applying effects",
        "Building video",
    ]
    bar = tqdm(steps, desc="yt2karaoke", unit="step")

    try:
        # --- Step 1: Download ---
        bar.set_description(steps[0])
        from .downloader import download_audio, get_video_info

        video_info = get_video_info(config.youtube_url)
        safe_title = _safe_filename(video_info.get("title", "karaoke"))
        stem_name = config.output_filename or safe_title

        audio_path = download_audio(
            config.youtube_url,
            output_dir=work_dir,
            filename=stem_name,
            audio_format="wav",
        )
        bar.update()

        # --- Step 2: Separate ---
        bar.set_description(steps[1])
        if config.track2stem_url:
            from .separator import Track2StemClient

            client = Track2StemClient(config.track2stem_url)
            stems = client.separate(
                audio_path,
                work_dir / "stems",
                vocals_volume=config.vocals_volume,
            )
        else:
            from .separator import separate

            stems = separate(
                audio_path,
                output_dir=work_dir / "stems",
                model=config.separation_model,
                vocals_volume=config.vocals_volume,
            )
        instrumental_path = stems["instrumental"]
        vocals_path = stems["vocals"]
        bar.update()

        # --- Step 3: Transcribe ---
        bar.set_description(steps[2])
        from .transcriber import transcribe, lines_to_lrc, lines_to_ass

        lyrics = transcribe(
            vocals_path,
            model_size=config.whisper_model,
            language=config.language,
        )
        lrc_path = output_dir / f"{stem_name}.lrc"
        ass_path = output_dir / f"{stem_name}.ass"
        lrc_path.write_text(lines_to_lrc(lyrics), encoding="utf-8")
        ass_path.write_text(
            lines_to_ass(lyrics, width=config.video_width, height=config.video_height),
            encoding="utf-8",
        )
        bar.update()

        # --- Step 4: Effects ---
        bar.set_description(steps[3])
        processed_vocals: Optional[Path] = None
        if config.vocals_volume > 0:
            from .effects import apply_effects

            fx_path = work_dir / f"{stem_name}_vocals_fx.wav"
            try:
                apply_effects(
                    vocals_path,
                    fx_path,
                    reverb=config.apply_reverb,
                    delay=config.apply_delay,
                    distortion=config.apply_distortion,
                    chorus=config.apply_chorus,
                )
                processed_vocals = fx_path
            except Exception:
                # Fallback to raw vocals if effects fail
                processed_vocals = vocals_path
        bar.update()

        # --- Step 5: Video ---
        bar.set_description(steps[4])
        from .video import build_video

        video_out = output_dir / f"{stem_name}.mp4"
        build_video(
            instrumental_path,
            lyrics,
            video_out,
            width=config.video_width,
            height=config.video_height,
            fps=config.fps,
            visual_style=config.visual_style,
            visual_speed=config.visual_speed,
            font_size=config.font_size,
            vocals_path=processed_vocals,
            vocals_volume=config.vocals_volume,
        )
        bar.update()

        # Copy stems to output dir
        final_instrumental = output_dir / f"{stem_name}_instrumental.wav"
        final_vocals = output_dir / f"{stem_name}_vocals.wav"
        if not final_instrumental.exists():
            import shutil
            shutil.copy2(instrumental_path, final_instrumental)
        if not final_vocals.exists():
            import shutil
            shutil.copy2(vocals_path, final_vocals)

        return KaraokeResult(
            video_path=video_out,
            instrumental_path=final_instrumental,
            vocals_path=final_vocals,
            lyrics_lrc_path=lrc_path,
            lyrics_ass_path=ass_path,
        )
    finally:
        bar.close()
        if _cleanup_work_dir:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)


def _safe_filename(name: str) -> str:
    """Strip characters that are invalid in file names."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()")
    safe = "".join(c if c in keep else "_" for c in name)
    return safe.strip()[:100]
