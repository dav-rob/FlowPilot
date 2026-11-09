"""Quota, partition and family-assignment planning. Pure functions of (seed, size)."""
from __future__ import annotations

from .schema import CROSS, DIFFICULTIES, DIFFICULTY_SHARE, DISTRACTOR, DOMAINS, GROUPS, PARTITIONS, PARTITION_SHARE
from .util import sub_rng

MIN_SIZE = 42
MAX_SIZE = 20000
DEFAULT_SIZE = 250
GROUP_SHARE = {**{d: 40 / 250 for d in DOMAINS}, CROSS: 25 / 250, DISTRACTOR: 25 / 250}


def largest_remainder(total: int, shares: list[float], minimum: int = 0) -> list[int]:
    raw = [total * s for s in shares]
    out = [max(minimum, int(x)) for x in raw]
    # fix the sum: add to largest remainders, remove from largest counts above minimum
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - int(raw[i])))
    i = 0
    while sum(out) < total:
        out[order[i % len(order)]] += 1
        i += 1
    while sum(out) > total:
        j = max((k for k in range(len(out)) if out[k] > minimum), key=lambda k: out[k])
        out[j] -= 1
    return out


def group_quotas(size: int) -> dict[str, int]:
    if size == DEFAULT_SIZE:
        return {**{d: 40 for d in DOMAINS}, CROSS: 25, DISTRACTOR: 25}
    q = largest_remainder(size, [GROUP_SHARE[g] for g in GROUPS], minimum=len(PARTITIONS))
    return dict(zip(GROUPS, q))


def cell_quotas(size: int) -> dict[tuple[str, str], int]:
    out = {}
    for g, n in group_quotas(size).items():
        parts = largest_remainder(n, [PARTITION_SHARE[p] for p in PARTITIONS], minimum=1)
        for p, c in zip(PARTITIONS, parts):
            out[(p, g)] = c
    return out


def assign_families(seed: int, families_by_group: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    """Whole-family holdout: every partition gets >=1 family per group; no family appears in two partitions."""
    plan: dict[str, dict[str, str]] = {}
    for g, fams in families_by_group.items():
        if len(fams) < len(PARTITIONS):
            raise ValueError(f"group {g!r} needs at least {len(PARTITIONS)} families, has {len(fams)}")
        order = sorted(fams)
        sub_rng(seed, "family-assignment", g).shuffle(order)
        plan[g] = {order[0]: "test", order[1]: "validation", **{f: "train" for f in order[2:]}}
    return plan


def deal_difficulties(seed: int, cell_sizes: list[tuple[tuple[str, str], int]]) -> dict[tuple[str, str], list[str]]:
    """Largest-deficit dealing: global totals track 50/30/20 (exact when divisible) and each stratum stays near it."""
    out, alloc, cum, cur = {}, [0, 0, 0], 0, None
    rng = sub_rng(seed, "difficulty")
    for key, n in cell_sizes:
        if key[0] != cur:  # deal per partition so every partition tracks 50/30/20
            cur, alloc, cum = key[0], [0, 0, 0], 0
        lst = []
        for _ in range(n):
            cum += 1
            i = max(range(3), key=lambda k: (cum * DIFFICULTY_SHARE[k] - alloc[k], -k))
            alloc[i] += 1
            lst.append(DIFFICULTIES[i])
        rng.shuffle(lst)
        out[key] = lst
    return out


def validate_params(seed, size) -> tuple[int, int]:
    if isinstance(seed, bool) or not isinstance(seed, int) or not (0 <= seed < 2**63):
        raise ValueError("seed must be an integer in [0, 2**63)")
    if isinstance(size, bool) or not isinstance(size, int) or not (MIN_SIZE <= size <= MAX_SIZE):
        raise ValueError(f"size must be an integer between {MIN_SIZE} and {MAX_SIZE} (every partition x group cell needs at least one case)")
    return seed, size
