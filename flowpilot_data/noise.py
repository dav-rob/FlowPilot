"""Controlled text noise. Only purely alphabetic words are mutated, so identifiers, amounts and dates stay intact."""
from __future__ import annotations

import re

from .util import Rng

_WORD = re.compile(r"[A-Za-z]{4,}")
_OCR = [("rn", "m"), ("cl", "d"), ("l", "1"), ("O", "0"), ("S", "5"), ("e", "c"), ("vv", "w"), ("li", "h")]


def _typo(word: str, rng: Rng) -> str:
    i = rng.randrange(1, len(word) - 2)
    kind = rng.randrange(3)
    if kind == 0:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind == 1:
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]


def _ocr_word(word: str, rng: Rng) -> str:
    cands = [(a, b) for a, b in _OCR if a in word]
    if not cands:
        return word
    a, b = rng.pick(cands)
    return word.replace(a, b, 1)


def apply_noise(text: str, rng: Rng, level: int, mode: str = "typo", protect: frozenset = frozenset()) -> str:
    """level 0 = none, 1 = minor, 2 = heavy. mode 'ocr' uses scanner-style substitutions."""
    if level <= 0:
        return text
    rate = {1: 0.025, 2: 0.07}[level]
    protect = frozenset(str(w).lower() for w in protect)
    fn = _ocr_word if mode == "ocr" else _typo

    punct = ".,;:!?()[]\"'"

    def sub(m: re.Match) -> str:
        chunk = m.group(0)
        core = chunk.strip(punct)
        if len(core) < 4 or not core.isalpha() or core.lower() in protect or rng.random() >= rate:
            return chunk
        return chunk.replace(core, fn(core, rng), 1)

    out = [re.sub(r"\S+", sub, line) for line in text.split("\n")]
    s = "\n".join(out)
    if level == 2 and mode == "ocr":
        lines = s.split("\n")
        def split(l: str) -> str:
            if len(l) < 60 or rng.random() < 0.7 or " " not in l[len(l) // 2:]:
                return l
            i = l.index(" ", len(l) // 2)
            return l[:i] + "\n" + l[i + 1:]
        s = "\n".join(split(l) for l in lines)
    return s


_SWAPS = {"1": "l", "l": "1", "0": "O", "O": "0", "5": "S", "S": "5", "8": "B", "B": "8"}


def corrupt_identifier(ident: str, rng: Rng) -> str:
    """OCR-style single-character corruption of the hex part of an ID, guaranteed to differ from the input."""
    head, _, tail = ident.rpartition("-")
    idxs = [i for i, c in enumerate(tail) if c in _SWAPS]
    if not idxs:
        return head + "-" + tail[:-1] + ("X" if tail[-1] != "X" else "Y")
    i = rng.pick(idxs)
    return f"{head}-{tail[:i]}{_SWAPS[tail[i]]}{tail[i + 1:]}"
