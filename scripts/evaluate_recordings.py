"""Reproduce evaluation of recorded live decisions without new model/tool calls."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flowpilot.evaluation import prediction
from flowpilot_data.evaluate import evaluate, load_truth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional report JSON output path")
    args = parser.parse_args()
    runs = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "examples" / "traces").glob("*.json"))
    ]
    if not runs:
        raise SystemExit("No recorded showcases found.")
    cases = {r["case_id"] for r in runs}
    truths = [t for t in load_truth(ROOT, "train") if t["case_id"] in cases]
    if {t["case_id"] for t in truths} != cases:
        raise SystemExit(
            "Recordings do not match this dataset. Use the checked-in dataset or record new investigations."
        )
    report = evaluate(truths, [prediction(r) for r in runs], include_cases=True)
    report["warning"] = (
        "Evaluation of five curated recorded live training showcases after integration fixes; not a held-out benchmark. Usage and latency describe the original executions. No new model/tool calls were made."
    )
    report["source_run_ids"] = [r["id"] for r in runs]
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"Wrote recorded-live evaluation to {args.out}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
