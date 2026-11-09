"""Dataset generation: plan -> build worlds/cases/truth -> render -> write -> atomic-ish install."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from .docs import choose_format, choose_voice, render_attachment, render_primary
from .planning import DEFAULT_SIZE, assign_families, cell_quotas, deal_difficulties, validate_params
from .scenarios import FAMILIES
from .scenarios.base import Ctx
from .schema import GROUPS, PARTITIONS, TABLES
from .showcase import select_showcases
from .util import GENERATOR_VERSION, MARKER_FILE, REFERENCE_NOW, Rng, digest, sub_rng, ts, write_json, write_jsonl
from .world import World, background

OWNED = {"data": ["partitions", "README.md"], "evaluation": ["ground_truth", "manifests", "showcase", "schema"]}


def plan_slots(seed: int, size: int, allow_partial: bool = False) -> tuple[list[dict], dict]:
    by_group: dict[str, list[str]] = {g: [] for g in GROUPS}
    for f in FAMILIES.values():
        by_group[f.group].append(f.id)
    missing = [g for g, v in by_group.items() if len(v) < len(PARTITIONS)]
    if missing and not allow_partial:
        raise ValueError(f"groups without enough scenario families: {missing}")
    assign = assign_families(seed, {g: v for g, v in by_group.items() if len(v) >= len(PARTITIONS)}) if not allow_partial else {
        g: dict(zip(sorted(v), (PARTITIONS * 3)[:len(v)])) for g, v in by_group.items() if v}
    quotas = cell_quotas(size)
    cells = [((p, g), quotas[(p, g)]) for p in PARTITIONS for g in GROUPS if g in assign]
    diffs = deal_difficulties(seed, cells)
    slots: list[dict] = []
    for (p, g), n in cells:
        fams = sorted(f for f, part in assign[g].items() if part == p)
        rng = sub_rng(seed, "slots", p, g)
        per_fam = Counter(fams[i % len(fams)] for i in range(n))
        cell_slots = []
        for f in fams:
            variants = list(FAMILIES[f].variants)
            rng.shuffle(variants)
            for j in range(per_fam[f]):
                cell_slots.append({"partition": p, "group": g, "family": f, "variant": variants[j % len(variants)]})
        rng.shuffle(cell_slots)                     # variant order independent of the difficulty list below
        for s, d in zip(cell_slots, diffs[(p, g)]):
            s["difficulty"] = d
        slots.extend(cell_slots)
    return slots, assign


def _write_doc(root: Path, partition: str, case_id: str, ctx: Ctx, seed: int) -> dict:
    rr = sub_rng(seed, partition, case_id, "render")
    fmt, voice = choose_format(rr), choose_voice(rr)
    spec = ctx.doc
    files = [render_primary(spec, rr, fmt, voice, ctx.quality, f"EVT-{digest(seed, case_id)[:8].upper()}")]
    protect = frozenset(spec.protect)
    files += [render_attachment(a, rr, ctx.quality, protect) for a in spec.attachments]
    docs = []
    for i, rf in enumerate(files):
        did = f"DOC-{digest(seed, partition, case_id, 'doc', i)[:10].upper()}"
        rel = f"inbox/{did}.{rf.ext}"
        path = root / "partitions" / partition / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = rf.text.encode("utf-8")
        path.write_bytes(data)
        docs.append({"document_id": did, "path": rel, "media_type": rf.media_type, "bytes": len(data), "sha256": digest(rf.text)})
    return {"case_id": case_id, "partition": partition, "received_at": spec.sent_at, "document": docs[0], "attachments": docs[1:]}


def build(seed: int, size: int, staging: Path, allow_partial: bool = False) -> dict:
    seed, size = validate_params(seed, size)
    slots, assign = plan_slots(seed, size, allow_partial)
    data_root, eval_root = staging / "data", staging / "evaluation"
    truths: dict[str, list[dict]] = {p: [] for p in PARTITIONS}
    cases_pub: dict[str, list[dict]] = {p: [] for p in PARTITIONS}
    for p in PARTITIONS:
        mine = [s for s in slots if s["partition"] == p]
        if not mine:
            continue
        w = World(seed, p)
        background(w, sub_rng(seed, p, "background"), len(mine) // 6)
        order = list(mine)
        sub_rng(seed, p, "case-order").shuffle(order)
        for n, s in enumerate(order):
            cid = f"IN-{digest(seed, p, 'case', n)[:10].upper()}"
            ctx = Ctx(w, cid, FAMILIES[s["family"]], s["variant"], s["difficulty"], p)
            ctx.fam.build(ctx)
            assert ctx.truth is not None, s
            ctx.truth["group"] = s["group"]
            pub = _write_doc(data_root, p, cid, ctx, seed)
            truths[p].append(ctx.truth)
            cases_pub[p].append(pub)
        for t, rows in w.tables.items():
            write_jsonl(data_root / "partitions" / p / "enterprise" / f"{t}.jsonl", sorted(rows, key=lambda r: r["id"]))
        write_jsonl(data_root / "partitions" / p / "cases.jsonl", sorted(cases_pub[p], key=lambda r: r["case_id"]))
        write_jsonl(eval_root / "ground_truth" / f"{p}.jsonl", sorted(truths[p], key=lambda r: r["case_id"]))
    showcase = select_showcases(truths, cases_pub)
    manifest = dataset_manifest(seed, size, truths, assign, showcase)
    write_json(eval_root / "manifests" / "dataset_manifest.json", manifest)
    write_json(eval_root / "manifests" / "splits.json", split_manifest(seed, truths, assign))
    write_json(eval_root / "showcase" / "showcase_cases.json", showcase)
    (eval_root / "showcase" / "SHOWCASE_GUIDE.md").write_text(showcase_guide(showcase, truths, cases_pub), encoding="utf-8")
    schema_dir = eval_root / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "prediction_schema.md").write_text(PREDICTION_SCHEMA_DOC, encoding="utf-8")
    (data_root / "README.md").write_text(DATA_README, encoding="utf-8")
    return manifest


PREDICTION_SCHEMA_DOC = """# Prediction, Tool-Trace and Usage Schema

`flowpilot_data.evaluate` (and `python -m flowpilot_data evaluate`) consumes **caller-provided** JSONL predictions (`one JSON object per line`).
No model is invoked by this package, and no synthetic JEV scores, confidences, token counts, latencies, or costs are fabricated: any omitted metric field is reported as `null` / `0` coverage.

## JSONL Record Format

```json
{
  "case_id": "IN-B148DF6144",
  "system": "jev_only",
  "routing": {
    "primary_category": "supplier_fraud",
    "secondary_categories": [],
    "abstained": false,
    "escalated": false,
    "needs_investigation": true,
    "risk_level": "critical",
    "confidence": 0.84
  },
  "outcome": {
    "action": "hold_payment_and_open_fraud_case",
    "by_workflow": {
      "supplier_fraud": "hold_payment_and_open_fraud_case"
    },
    "cited_evidence": ["SUP-47D4A998", "MSG-0C0E250E"],
    "executed_sensitive_actions": ["place_payment_hold"]
  },
  "tool_trace": [
    {
      "tool": "search_invoices",
      "arguments": {"invoice_number": "SI-79253"},
      "ok": true,
      "error_code": null,
      "latency_ms": 12.4
    }
  ],
  "usage": {
    "input_tokens": 1420,
    "output_tokens": 310,
    "cost_usd": 0.0021,
    "latency_ms": 640.0
  },
  "demo_fixture": false
}
```

## Field Reference

| Field | Type | Description |
|---|---|---|
| `case_id` | `str` (required) | Case identifier matching `data/partitions/<split>/cases.jsonl` and `evaluation/ground_truth/<split>.jsonl`. |
| `system` | `str` | System identifier (e.g. `"jev_only"` or `"jev_plus_escalation"`). Used to filter single-system runs or pair records in `compare()`. |
| `routing.primary_category` | `str \\| null` | Predicted primary workflow (`supplier_fraud`, `regulatory_compliance`, `gdpr_data`, `it_asset`, `contract_risk`, `out_of_scope`), or `null` when `abstained=true`. |
| `routing.secondary_categories` | `list[str]` | Additional workflows predicted for cross-domain cases. Combined with `primary_category` for multi-label precision/recall/F1 and FP/FN counts. |
| `routing.abstained` | `bool` | Whether the router abstained from workflow assignment. |
| `routing.escalated` | `bool` | Whether the case was escalated from JEV to a stronger reasoning model. |
| `routing.needs_investigation` | `bool \\| null` | Optional prediction of whether tool calls are required. |
| `routing.risk_level` | `str \\| null` | Optional predicted risk level (`low`, `medium`, `high`, `critical`). |
| `routing.confidence` | `float \\| null` | Optional **actual** model confidence in `[0.0, 1.0]` recorded at runtime. Used to compute mean confidence on correct/incorrect primary predictions, Brier score, and `threshold_calibration` for JEV escalation thresholds. Never generated by the dataset builder. |
| `outcome.action` | `str \\| null` | Final business action selected by the agent (see `flowpilot_data.schema.OUTCOMES`). |
| `outcome.by_workflow` | `dict[str, str]` | Optional per-workflow outcome map for multi-workflow cases. |
| `outcome.cited_evidence` | `list[str]` | Record IDs cited to justify the outcome. Checked against decisive and known case records. |
| `outcome.executed_sensitive_actions` | `list[str]` | Sensitive tools executed during the case. |
| `tool_trace` | `list[object]` | Ordered tool calls with `tool`, `arguments`, `ok` (`bool`), `error_code` (`str \\| null`), and optional `latency_ms` (`float \\| null`). |
| `usage` | `object` | Optional runtime telemetry: `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`. Omitted values are reported as missing (`cases_with_cost`, `cases_with_latency`, `cases_with_tokens`), never estimated. `usage.latency_ms` measures end-to-end time; complete tool timings are reported separately as `mean_tool_duration_sum_ms` and are not a substitute for wall-clock latency. |
| `demo_fixture` | `bool` | Optional flag. If `true` on any record, the evaluator attaches a prominent warning that the file contains scripted fixtures rather than real model outputs. |

Files containing multiple systems require `--system <name>` for single-system scoring or `--compare` for paired scoring; records from different systems are never merged.

## Paired Comparison (`jev_only` vs `jev_plus_escalation`)

When a predictions JSONL file contains records for two systems (by default `system="jev_only"` and `system="jev_plus_escalation"`), `python -m flowpilot_data evaluate --predictions <file> --compare jev_only jev_plus_escalation`:

1. Computes coverage for each system (`truth_cases`, `predicted_a`, `predicted_b`, `paired`, `only_in_a`, `only_in_b`, `missing_in_both`).
2. Evaluates `paired_metrics` strictly over the intersection of cases predicted by both systems.
3. Computes paired transitions (`b_fixes_a`, `b_regresses_a`, `unchanged`, exact two-sided binomial `sign_test_p`), accuracy on the `escalated_subset`, `cost_delta` where both systems report `cost_usd`, and metric deltas (`deltas_b_minus_a`).
"""


DATA_README = """# Agent-visible data

`partitions/<name>/` holds one self-contained synthetic enterprise environment:

* `cases.jsonl` - incoming cases (opaque ids, received time, document references). No labels.
* `inbox/` - incoming documents and attachments (email, text, markdown, JSON events, JSONL event streams, OCR text, CSV).
* `enterprise/*.jsonl` - business system records queried by the mock tools (`flowpilot_data.tools`).

Everything is fictional. Ground truth is kept outside this directory in `evaluation/`.
"""


def dataset_manifest(seed, size, truths, assign, showcase) -> dict:
    allt = [t for p in PARTITIONS for t in truths[p]]
    def cnt(key):
        return dict(sorted(Counter(key(t) for t in allt).items()))
    by_part = {p: {"cases": len(truths[p]), "by_group": dict(sorted(Counter(t["group"] for t in truths[p]).items())),
                   "by_difficulty": dict(sorted(Counter(t["difficulty"] for t in truths[p]).items()))} for p in PARTITIONS}
    return {"generator_version": GENERATOR_VERSION, "seed": seed, "size": size, "reference_now": ts(REFERENCE_NOW), "total_cases": len(allt),
            "by_group": cnt(lambda t: t["group"]), "by_difficulty": cnt(lambda t: t["difficulty"]),
            "difficulty_fractions": {k: round(v / len(allt), 3) for k, v in cnt(lambda t: t["difficulty"]).items()},
            "by_primary_category": cnt(lambda t: t["routing"]["primary_category"]), "by_outcome": cnt(lambda t: t["expected_outcome"]["action"]),
            "by_risk": cnt(lambda t: t["risk_level"]), "by_document_quality": cnt(lambda t: t["document_quality"]),
            "abstain_expected": sum(t["routing"]["abstain_expected"] for t in allt), "escalation_expected": sum(t["routing"]["escalate_to_stronger_model_expected"] for t in allt),
            "multi_label": sum(len(t["routing"]["labels"]) > 1 for t in allt), "human_review_required": sum(t["human_review_required"] for t in allt),
            "by_partition": by_part, "note": "Intended difficulty levels only. No model scores are generated."}


def split_manifest(seed, truths, assign) -> dict:
    return {"seed": seed, "policy": "whole scenario families are held out: no family appears in more than one partition",
            "family_to_partition": {g: dict(sorted(a.items())) for g, a in assign.items()},
            "cases": {p: sorted(t["case_id"] for t in truths[p]) for p in PARTITIONS}}


def showcase_guide(showcase, truths, cases_pub) -> str:
    byid = {t["case_id"]: t for p in PARTITIONS for t in truths[p]}
    pub = {c["case_id"]: c for p in PARTITIONS for c in cases_pub[p]}
    lines = ["# Showcase guide (evaluator/presenter only - not agent input)", "",
             "Five curated cases, one per workflow, drawn from the **train** partition so the held-out test set is not spent on demos.",
             "Selection is automatic and deterministic: highest score for dependent investigation depth, alternative paths, outages, conflicting evidence and risk.",
             "The `example_path` below is a presenter/evaluator walkthrough fixture illustrating one valid investigation trajectory; an AI agent receives only the public case input and selects tools dynamically.",
             "Run a walkthrough: `python -m flowpilot_data showcase` (or `--case <case_id>` / `--workflow <workflow>`).", ""]
    for s in showcase["cases"]:
        t = byid[s["case_id"]]
        d = pub[s["case_id"]]["document"]
        lines += [f"## {s['workflow']}: `{s['case_id']}`", f"* Input: `data/partitions/{t['partition']}/{d['path']}`",
                  f"* Scenario: {t['scenario_summary']}", f"* Expected outcome: `{t['expected_outcome']['action']}` (risk {t['risk_level']}, human review {t['human_review_required']})",
                  f"* Why it demos well: {', '.join(s['reasons'])}", "* Evidence a good investigation finds: " + ", ".join(f"`{e['record_id']}` ({e['supports']})" for e in t["evidence"] if e["role"] in ("decisive", "contradicting")),
                  "* Example valid path (presenter fixture; others exist): " + " -> ".join(f"`{x['tool']}`" for x in s["example_path"]), ""]
    return "\n".join(lines)


# -- safe install --------------------------------------------------------------------------
def check_out_root(out_root: str | os.PathLike) -> Path:
    p = Path(out_root).expanduser()
    if ".." in p.parts:
        raise ValueError("output path must not contain '..'")
    p = p.resolve()
    if p == Path(p.anchor) or p == Path.home().resolve() or len(p.parts) < 3:
        raise ValueError(f"refusing to generate directly into {p}")
    if p.exists() and not p.is_dir():
        raise ValueError(f"{p} exists and is not a directory")
    return p


def install(staging: Path, out_root: Path) -> None:
    """Replace only generator-owned sub-paths, and only where a generator marker proves ownership."""
    for top, subs in OWNED.items():
        dest = out_root / top
        existing = [dest / s for s in subs if (dest / s).exists()]
        if existing and not (dest / MARKER_FILE).exists():
            raise FileExistsError(f"{dest} contains {[e.name for e in existing]} but no {MARKER_FILE} marker; refusing to overwrite")
    for top, subs in OWNED.items():
        dest = out_root / top
        dest.mkdir(parents=True, exist_ok=True)
        for s in subs:
            src, tgt = staging / top / s, dest / s
            if not src.exists():
                continue
            if tgt.exists():
                shutil.rmtree(tgt) if tgt.is_dir() else tgt.unlink()
            shutil.move(str(src), str(tgt))
        (dest / MARKER_FILE).write_text(json.dumps({"generator_version": GENERATOR_VERSION, "owned": subs}) + "\n", encoding="utf-8")


def generate(out_root: str | os.PathLike = ".", seed: int = 42, size: int = DEFAULT_SIZE, allow_partial: bool = False) -> dict:
    seed, size = validate_params(seed, size)
    out = check_out_root(out_root)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".flowpilot_stage_", dir=out) as tmp:
        stage = Path(tmp)
        manifest = build(seed, size, stage, allow_partial)
        install(stage, out)
    return manifest
