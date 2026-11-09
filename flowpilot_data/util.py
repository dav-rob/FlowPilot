"""Deterministic helpers: hashing, seeded RNG, dates, JSON/JSONL IO. No wall-clock use."""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

# Fixed reference "now" for the synthetic enterprise (never the wall clock).
REFERENCE_NOW = datetime(2026, 9, 14, 9, 0, 0)
GENERATOR_VERSION = "1.0.0"
MARKER_FILE = ".flowpilot_generated"


def digest(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()


class Rng(random.Random):
    """random.Random with a few convenience helpers."""

    def pick(self, seq):
        return seq[self.randrange(len(seq))]

    def chance(self, p: float) -> bool:
        return self.random() < p

    def weighted(self, pairs):
        """pairs: [(item, weight)]"""
        total = sum(w for _, w in pairs)
        x = self.random() * total
        for item, w in pairs:
            x -= w
            if x <= 0:
                return item
        return pairs[-1][0]

    def hex(self, n: int) -> str:
        return "".join(self.choice("0123456789ABCDEF") for _ in range(n))

    def digits(self, n: int) -> str:
        return "".join(self.choice("0123456789") for _ in range(n))


def sub_rng(*keys: Any) -> Rng:
    return Rng(int(digest(*keys)[:16], 16))


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(days: float = 0, hours: float = 0, minutes: float = 0, rng: Rng | None = None) -> str:
    dt = REFERENCE_NOW - timedelta(days=days, hours=hours, minutes=minutes)
    if rng is not None:
        dt -= timedelta(minutes=rng.randrange(0, 600))
    return ts(dt)


def day(days_ago: float) -> str:
    return (REFERENCE_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def future_day(days: int) -> str:
    return (REFERENCE_NOW + timedelta(days=days)).strftime("%Y-%m-%d")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hash(root: Path) -> str:
    """Hash of all files below root (relative path + content), order independent of FS."""
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.name != ".DS_Store":
            h.update(str(p.relative_to(root)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def money(x: float) -> str:
    return f"£{x:,.2f}"
