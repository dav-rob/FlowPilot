"""Execution provenance frozen when a review or evaluation is created."""

from functools import lru_cache
from pathlib import Path
import subprocess


@lru_cache(maxsize=1)
def application_revision():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
