"""Run the dependency-free, signal-level AudioWorklet tests with Node."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="AudioWorklet DSP checks require Node.js")
def test_pitch_processor_signals():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "--test", str(root / "tests/js/pitch-processor.test.cjs")],
        capture_output=True, text=True, cwd=root, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
