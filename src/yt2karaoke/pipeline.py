"""Main pipeline: orchestrates the full YouTube → karaoke conversion."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class KaraokeConfig:
    """Configuration for a single karaoke processing job."""

    # Input
    youtube_url: str = ""

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
    audio_path: Optional[str | os.PathLike] = None
    lyrics_path: Optional[str | os.PathLike] = None
    title: str = ""


@dataclass
class KaraokeResult:
    """Paths to the output artefacts from a completed pipeline run."""

    video_path: Path
    instrumental_path: Path
    vocals_path: Path
    lyrics_lrc_path: Optional[Path] = None
    lyrics_ass_path: Optional[Path] = None
    lyrics_json_path: Optional[Path] = None
    title: str = ""
    duration: float = 0.0


def run(
    config: KaraokeConfig,
    *,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> KaraokeResult:
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
    import soundfile as sf
    from tqdm import tqdm
    from .video import validate_vocals_volume
    from .transcriber import TranscriptionError

    validate_vocals_volume(config.vocals_volume)
    if bool(config.youtube_url) == bool(config.audio_path):
        raise ValueError("Provide exactly one YouTube URL or local audio_path.")
    if config.audio_path and not Path(config.audio_path).is_file():
        raise FileNotFoundError(f"Audio file not found: {config.audio_path}")
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    last_progress: Optional[tuple[str, int]] = None

    def report(stage: str, progress: int) -> None:
        nonlocal last_progress
        if last_progress == (stage, progress):
            return
        last_progress = (stage, progress)
        if on_progress:
            on_progress(stage, progress)

    with ExitStack() as stack:
        if config.work_dir:
            work_dir = Path(config.work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            work_dir = Path(stack.enter_context(
                tempfile.TemporaryDirectory(dir=output_dir, prefix=".yt2karaoke_work_")
            ))
        bar = stack.enter_context(tqdm(total=5, desc="yt2karaoke", unit="step"))

        report("Preparing audio" if config.audio_path else "Downloading audio", 0)
        from .downloader import download_audio, get_video_info

        if config.audio_path:
            audio_path = Path(config.audio_path)
            title = config.title or audio_path.stem
        else:
            video_info = get_video_info(config.youtube_url)
            title = config.title or video_info.get("title", "karaoke")
            audio_path = None
        stem_name = _safe_filename(config.output_filename or title)
        input_paths = {
            Path(path).resolve() for path in (config.audio_path, config.lyrics_path) if path
        }
        output_names = [
            f"{stem_name}{suffix}" for suffix in (
                ".mp4", ".lrc", ".ass", ".lyrics.json", "_instrumental.wav", "_vocals.wav",
            )
        ]
        if any((output_dir / name).resolve() in input_paths for name in output_names):
            raise ValueError("Output would overwrite an input file. Choose a different output directory or filename.")
        if audio_path is None:
            audio_path = download_audio(
                config.youtube_url,
                output_dir=work_dir,
                filename=stem_name,
                audio_format="wav",
            )
        bar.update()

        report("Separating vocals", 20)
        bar.set_description("Separating vocals")
        if config.track2stem_url:
            from .separator import Track2StemClient

            client = Track2StemClient(config.track2stem_url)
            stems = client.separate(
                audio_path,
                work_dir / "stems",
                vocals_volume=1.0,
            )
        else:
            from .separator import separate

            stems = separate(
                audio_path,
                output_dir=work_dir / "stems",
                model=config.separation_model,
                vocals_volume=1.0,
            )
        instrumental_path = stems["instrumental"]
        vocals_path = stems["vocals"]
        duration = sf.info(instrumental_path).duration
        bar.update()

        report("Syncing lyrics", 45)
        bar.set_description("Syncing lyrics")
        from .transcriber import transcribe, load_lyrics, lines_to_lrc, lines_to_ass, lines_to_json

        if config.lyrics_path:
            lyrics = load_lyrics(config.lyrics_path, duration=duration)
        else:
            lyrics = transcribe(
                vocals_path,
                model_size=config.whisper_model,
                language=config.language,
            )
        if not lyrics:
            raise TranscriptionError(
                "No lyrics were detected. Try a larger Whisper model or provide timed lyrics JSON."
            )
        lrc_path = output_dir / f"{stem_name}.lrc"
        ass_path = output_dir / f"{stem_name}.ass"
        json_path = output_dir / f"{stem_name}.lyrics.json"
        lrc_path.write_text(lines_to_lrc(lyrics), encoding="utf-8")
        ass_path.write_text(
            lines_to_ass(lyrics, width=config.video_width, height=config.video_height),
            encoding="utf-8",
        )
        json_path.write_text(lines_to_json(lyrics), encoding="utf-8")
        bar.update()

        report("Preparing the mix", 60)
        processed_vocals = vocals_path if config.vocals_volume > 0 else None
        if config.vocals_volume > 0 and any((
            config.apply_reverb, config.apply_delay, config.apply_distortion, config.apply_chorus,
        )):
            from .effects import apply_effects

            fx_path = work_dir / f"{stem_name}_vocals_fx.wav"
            apply_effects(
                vocals_path,
                fx_path,
                reverb=config.apply_reverb,
                delay=config.apply_delay,
                distortion=config.apply_distortion,
                chorus=config.apply_chorus,
            )
            processed_vocals = fx_path
        bar.update()

        report("Rendering karaoke", 65)
        bar.set_description("Rendering karaoke")
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
            on_progress=lambda fraction: report("Rendering karaoke", 65 + int(fraction * 32)),
        )
        bar.update()

        final_instrumental = output_dir / f"{stem_name}_instrumental.wav"
        final_vocals = output_dir / f"{stem_name}_vocals.wav"
        if instrumental_path.resolve() != final_instrumental.resolve():
            shutil.copy2(instrumental_path, final_instrumental)
        if vocals_path.resolve() != final_vocals.resolve():
            shutil.copy2(vocals_path, final_vocals)

        report("Ready", 100)
        return KaraokeResult(
            video_path=video_out,
            instrumental_path=final_instrumental,
            vocals_path=final_vocals,
            lyrics_lrc_path=lrc_path,
            lyrics_ass_path=ass_path,
            lyrics_json_path=json_path,
            title=title,
            duration=duration,
        )


def _safe_filename(name: str) -> str:
    """Strip characters that are invalid in file names."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()")
    safe = "".join(c if c in keep else "_" for c in name)
    return safe.strip(" .")[:100] or "karaoke"
