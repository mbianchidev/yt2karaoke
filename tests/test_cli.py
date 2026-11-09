"""CLI source selection and vocal-gain validation."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from yt2karaoke.cli import main
from yt2karaoke.pipeline import KaraokeResult


def test_convert_requires_one_source():
    response = CliRunner().invoke(main, ["convert"])
    assert response.exit_code == 2
    assert "exactly one" in response.output


def test_convert_accepts_local_media(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"generated test fixture")
    result = KaraokeResult(source, source, source)
    with patch("yt2karaoke.pipeline.run", return_value=result) as run:
        response = CliRunner().invoke(main, [
            "convert", "--audio-file", str(source), "--vocals-volume", "0.25",
            "--no-reverb", "--no-delay",
        ])
    assert response.exit_code == 0
    config = run.call_args.args[0]
    assert config.audio_path == str(source)
    assert config.youtube_url == ""
    assert config.vocals_volume == 0.25


@pytest.mark.parametrize("volume", ["-0.1", "1.1"])
def test_convert_rejects_invalid_gain(volume):
    response = CliRunner().invoke(main, [
        "convert", "https://youtube.com/watch?v=synthetic", "--vocals-volume", volume,
    ])
    assert response.exit_code == 2
