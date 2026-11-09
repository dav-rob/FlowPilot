"""Command-line interface for `python -m flowpilot_data`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluate import compare, evaluate, load_jsonl, load_truth
from .generate import generate
from .planning import DEFAULT_SIZE
from .schema import DOMAINS, PARTITIONS
from .showcase import WALKTHROUGH_DISCLAIMER, format_walkthrough, run_walkthrough
from .util import read_json, write_json
from .validate import validate


def _cmd_generate(args: argparse.Namespace) -> int:
    manifest = generate(out_root=args.out, seed=args.seed, size=args.size)
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    out_path = Path(args.out).resolve()
    parts = ", ".join(f"{p}={manifest['by_partition'][p]['cases']}" for p in PARTITIONS)
    groups = ", ".join(f"{g}={n}" for g, n in manifest["by_group"].items())
    diffs = ", ".join(f"{d}={n}" for d, n in manifest["by_difficulty"].items())
    print(f"Generated FlowPilot dataset in {out_path}")
    print(f"  seed={manifest['seed']}  size={manifest['total_cases']}  version={manifest['generator_version']}")
    print(f"  partitions:  {parts}")
    print(f"  by_group:    {groups}")
    print(f"  difficulty:  {diffs}")
    print(f"  note:        {manifest['note']}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = args.out if args.out is not None else args.root
    rep = validate(root=root, replay_all=not args.no_replay)
    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        status = "OK" if rep["ok"] else "FAILED"
        print(
            f"Validation {status}: cases={rep['cases']} paths_replayed={rep['paths_replayed']} "
            f"max_cross_partition_similarity={rep['max_cross_partition_similarity']} "
            f"errors={len(rep['errors'])} warnings={len(rep['warnings'])}"
        )
        for w in rep["warnings"]:
            print(f"  warning: {w}")
        for e in rep["errors"][:25]:
            print(f"  error:   {e}", file=sys.stderr)
    return 0 if rep["ok"] else 1


def _cmd_showcase(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if args.list:
        sc_path = root / "evaluation" / "showcase" / "showcase_cases.json"
        if not sc_path.exists():
            raise FileNotFoundError(f"Showcase manifest not found at {sc_path}; run `python -m flowpilot_data generate` first")
        sc = read_json(sc_path)
        if args.json:
            print(json.dumps(sc, indent=2, sort_keys=True))
            return 0
        print(WALKTHROUGH_DISCLAIMER)
        print()
        for c in sc.get("cases", []):
            steps = " -> ".join(s["tool"] for s in c["example_path"])
            print(f"  {c['workflow']:22s}  {c['case_id']}  (partition={c['partition']}, score={c['score']})  path: {steps}")
        return 0

    walk = run_walkthrough(root=root, case_id=args.case, workflow=args.workflow)
    if args.json:
        print(json.dumps(walk, indent=2, sort_keys=True))
    else:
        print(format_walkthrough(walk))
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    pred_path = Path(args.predictions)
    if not pred_path.is_file():
        raise FileNotFoundError(f"Predictions JSONL file not found: {pred_path}")
    preds = load_jsonl(pred_path)
    if not preds:
        raise ValueError(f"Predictions file {pred_path} is empty")
    for i, rec in enumerate(preds, start=1):
        if not isinstance(rec, dict) or not rec.get("case_id"):
            raise ValueError(f"{pred_path}:{i}: prediction record must be a JSON object with a non-empty 'case_id'")

    truths = load_truth(args.root, partition=args.partition)
    if not truths:
        raise FileNotFoundError(
            f"No ground-truth records found under {Path(args.root) / 'evaluation' / 'ground_truth'}; "
            "run `python -m flowpilot_data generate` first"
        )

    if args.compare:
        sys_a, sys_b = args.compare
        report = compare(truths, preds, a=sys_a, b=sys_b)
    else:
        report = evaluate(truths, preds, system=args.system, include_cases=args.include_cases)

    if args.out:
        write_json(Path(args.out), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowpilot_data",
        description="FlowPilot synthetic enterprise dataset generator, mock tool walkthroughs, validator and offline evaluator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser(
        "generate",
        help="Deterministically generate data/ (agent-visible) and evaluation/ (private truth & manifests).",
    )
    p_gen.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed in [0, 2**63) (default: 42).")
    p_gen.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"Total cases to generate (default: {DEFAULT_SIZE}).")
    p_gen.add_argument("--out", default=".", help="Target root directory for data/ and evaluation/ (default: .).")
    p_gen.add_argument("--json", action="store_true", help="Print the full dataset manifest as JSON.")
    p_gen.set_defaults(func=_cmd_generate)

    p_val = sub.add_parser(
        "validate",
        help="Validate dataset schema, quotas, foreign-key references, evidence path replay, split isolation and zero leakage.",
    )
    p_val.add_argument("--root", default=".", help="Dataset root directory containing data/ and evaluation/ (default: .).")
    p_val.add_argument("--out", default=None, help="Alias for --root.")
    p_val.add_argument("--no-replay", action="store_true", help="Skip live mock-tool replay of every discovery path.")
    p_val.add_argument("--json", action="store_true", help="Print the validation report as JSON.")
    p_val.set_defaults(func=_cmd_validate)

    p_show = sub.add_parser(
        "showcase",
        help="Replay presenter walkthrough fixtures for the five curated showcase cases against the mock tools.",
    )
    p_show.add_argument("--root", default=".", help="Dataset root directory (default: .).")
    p_show.add_argument("--case", default=None, help="Specific showcase case_id to replay (default: all 5 showcases).")
    p_show.add_argument("--workflow", choices=DOMAINS, default=None, help="Filter showcase walkthrough to one workflow domain.")
    p_show.add_argument("--list", action="store_true", help="List the five curated showcase cases without full output.")
    p_show.add_argument("--json", action="store_true", help="Output walkthrough result as JSON.")
    p_show.set_defaults(func=_cmd_showcase)

    p_eval = sub.add_parser(
        "evaluate",
        help="Score caller-provided predictions, tool traces and usage against private ground truth (never runs a model or invents scores).",
    )
    p_eval.add_argument("--predictions", required=True, help="Path to caller-provided predictions JSONL file.")
    p_eval.add_argument("--root", default=".", help="Dataset root directory containing evaluation/ground_truth/ (default: .).")
    p_eval.add_argument("--partition", choices=PARTITIONS, default=None, help="Restrict ground truth to one partition (default: all).")
    p_eval.add_argument("--system", default=None, help="Filter single-system evaluation to records with this `system` name.")
    p_eval.add_argument(
        "--compare",
        nargs=2,
        metavar=("SYSTEM_A", "SYSTEM_B"),
        default=None,
        help="Run paired comparison between two systems in the predictions file (e.g. `--compare jev_only jev_plus_escalation`).",
    )
    p_eval.add_argument("--include-cases", action="store_true", help="Include per-case scoring breakdown in single-system output.")
    p_eval.add_argument("--out", default=None, help="Optional file path to write the JSON evaluation report.")
    p_eval.set_defaults(func=_cmd_evaluate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
