"""Load local application settings without executing shell code."""

import os
import shlex
from pathlib import Path

from .catalog import ROOT

JEV_SETTINGS = {"TYPESAFE_API_KEY", "JEV_API_KEY", "JEV_MODEL", "JEV_API_URL"}


def load_local_env(path: Path | None = None) -> None:
    path = Path(path) if path is not None else ROOT / ".env"
    if not path.exists():
        return
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.removeprefix("export ").partition("=")
        name = name.strip()
        if not separator:
            raise ValueError(f"Invalid configuration at {path.name} line {number}")
        if name not in JEV_SETTINGS and not name.startswith("FLOWPILOT_"):
            continue
        try:
            parts = shlex.split(value, comments=True)
        except ValueError:
            raise ValueError(f"Invalid quoting at {path.name} line {number}") from None
        if len(parts) > 1:
            raise ValueError(
                f"Quote values containing spaces at {path.name} line {number}"
            )
        os.environ.setdefault(name, parts[0] if parts else "")
