"""Showcase selection and live-demo walkthrough runner (evaluator/presenter side).

Selection and walkthroughs never change what agents see. Example paths in `showcase_cases.json`
are presenter fixtures illustrating one valid investigation path per case; an AI agent receives
only the public case input and selects tools dynamically.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .schema import DOMAINS
from .tools import EnterpriseEnv, EnterpriseSession
from .util import canonical, read_json, read_jsonl

ID_RE = re.compile(r"\b([A-Z]{1,4})-([0-9A-F]{8})\b")
WALKTHROUGH_DISCLAIMER = (
    "NOTE: Presenter/evaluator walkthrough fixture only (loaded from evaluation/showcase/showcase_cases.json). "
    "These example queries are NOT passed to the agent and do NOT prescribe a fixed tool sequence; "
    "an AI agent sees only data/partitions/<partition>/ and chooses tools dynamically."
)


def _score(t: dict) -> tuple[int, list[str]]:
    paths = [p for p in t["discoverability"]["paths"] if not p.get("blocked")]
    reasons = []
    s = 0
    d = t["discoverability"]["min_calls"]
    s += 3 * d
    if d >= 3:
        reasons.append(f"{d} dependent calls on the shortest path")
    if len(paths) >= 3:
        s += 2
        reasons.append(f"{len(paths)} valid investigation paths")
    if t["discoverability"]["unavailable_services"]:
        s += 3
        reasons.append("simulated service outage with recovery")
    if t["knobs"]["conflicting_evidence"]:
        s += 2
        reasons.append("conflicting evidence")
    if t["risk_level"] in ("high", "critical"):
        s += 3
        reasons.append(f"{t['risk_level']} risk with a sensitive action to withhold or approve")
    if t["routing"]["ambiguity"] != "none":
        s += 1
        reasons.append("category not clear from the input alone")
    if t["knobs"]["identifier_corrupted_in_input"]:
        s += 2
        reasons.append("corrupted identifier requires recovery")
    s += {"straightforward": 0, "moderate": 2, "difficult": 3}[t["difficulty"]]
    return s, reasons


def _build_example_path(t: dict) -> list[dict]:
    """Combine non-blocked discovery paths so the presenter fixture covers all decisive evidence and required groups."""
    paths = [p for p in t["discoverability"]["paths"] if not p.get("blocked")]
    if not paths:
        return []
    decisive = {e["record_id"] for e in t["evidence"] if e["role"] == "decisive"}
    all_ev = {e["record_id"] for e in t["evidence"]}
    ordered = sorted(
        paths,
        key=lambda p: (len(set(p.get("finds", [])) & decisive), len(set(p.get("finds", [])) & all_ev), len(p["steps"])),
        reverse=True,
    )
    steps: list[dict] = []
    seen_steps: set[str] = set()
    covered: set[str] = set()

    def _append_path(p: dict) -> None:
        for s in p["steps"]:
            key = canonical(s)
            if key not in seen_steps:
                seen_steps.add(key)
                steps.append(s)
        covered.update(p.get("finds", []))

    while decisive - covered:
        cur_tools = {s["tool"] for s in steps}
        best_p = max(
            ordered,
            key=lambda p: (
                len((set(p.get("finds", [])) & decisive) - covered),
                sum(1 for s in p["steps"] if s["tool"] in cur_tools),
                len(p["steps"]),
            ),
        )
        if not ((set(best_p.get("finds", [])) & decisive) - covered):
            break
        _append_path(best_p)

    for g in t["tools"].get("required_groups", []):
        opts = {(o["tool"], canonical(o["args"])) for o in g["any_of"]}
        if any((s["tool"], canonical(s["args"])) in opts for s in steps):
            continue
        for p in ordered:
            if any((s["tool"], canonical(s["args"])) in opts for s in p["steps"]):
                _append_path(p)
                break

    if not steps:
        _append_path(ordered[0])
    return steps


def select_showcases(truths: dict, cases_pub: dict) -> dict:
    out = []
    train = truths.get("train", [])
    for dom in DOMAINS:
        cands = [t for t in train if t["group"] == dom and t["routing"]["primary_category"] == dom]
        if not cands:
            continue
        best = max(cands, key=lambda t: (_score(t)[0], t["case_id"]))
        sc, reasons = _score(best)
        steps = _build_example_path(best)
        out.append({
            "workflow": dom,
            "case_id": best["case_id"],
            "partition": "train",
            "score": sc,
            "reasons": reasons or ["clear single-path investigation"],
            "example_path": steps,
        })
    return {
        "note": (
            "Evaluator/presenter fixture only. Curated automatically from the train partition. "
            "Example paths illustrate one valid investigation trajectory; agents receive only public case data "
            "and select tools dynamically."
        ),
        "cases": out,
    }


def run_walkthrough(
    root: str | Path = ".",
    case_id: str | None = None,
    workflow: str | None = None,
    retries: int = 3,
) -> dict:
    """Replay the presenter example path(s) from evaluation/showcase/showcase_cases.json against the mock tools."""
    root = Path(root)
    sc_path = root / "evaluation" / "showcase" / "showcase_cases.json"
    if not sc_path.exists():
        raise FileNotFoundError(f"Showcase manifest not found at {sc_path}; run `python -m flowpilot_data generate` first")
    showcase = read_json(sc_path)
    entries = list(showcase.get("cases", []))
    if case_id:
        entries = [e for e in entries if e["case_id"] == case_id]
        if not entries:
            avail = [e["case_id"] for e in showcase.get("cases", [])]
            raise ValueError(f"Unknown showcase case_id {case_id!r}; available showcase cases: {avail}")
    if workflow:
        entries = [e for e in entries if e["workflow"] == workflow]
        if not entries:
            avail = [e["workflow"] for e in showcase.get("cases", [])]
            raise ValueError(f"Unknown showcase workflow {workflow!r}; available workflows: {avail}")

    envs: dict[str, EnterpriseEnv] = {}
    truth_by_part: dict[str, dict[str, dict]] = {}
    pub_by_part: dict[str, dict[str, dict]] = {}

    results = []
    for entry in entries:
        part = entry["partition"]
        cid = entry["case_id"]
        if part not in envs:
            envs[part] = EnterpriseEnv(root / "data" / "partitions" / part)
            truth_by_part[part] = {t["case_id"]: t for t in read_jsonl(root / "evaluation" / "ground_truth" / f"{part}.jsonl")}
            pub_by_part[part] = {c["case_id"]: c for c in read_jsonl(root / "data" / "partitions" / part / "cases.jsonl")}

        env = envs[part]
        t = truth_by_part[part][cid]
        pub = pub_by_part[part][cid]
        doc_rel = pub["document"]["path"]
        doc_text = (root / "data" / "partitions" / part / doc_rel).read_text(encoding="utf-8")

        sess = EnterpriseSession(env, cid)
        step_traces = []
        discovered_ids: set[str] = set()
        for idx, step in enumerate(entry["example_path"], start=1):
            tool_name, args = step["tool"], step["args"]
            attempts = []
            res = None
            for attempt in range(1, retries + 1):
                res = sess.call(tool_name, **args)
                attempts.append({"attempt": attempt, "ok": res["ok"], "response": res})
                if res["ok"] or res["error"]["code"] != "SERVICE_UNAVAILABLE" or not res["error"].get("retryable"):
                    break
            blob = json.dumps(res.get("data") if res and res["ok"] else res.get("error", {}), sort_keys=True)
            found_here = sorted(set(m.group(0) for m in ID_RE.finditer(blob)))
            discovered_ids.update(found_here)
            step_traces.append({
                "step": idx,
                "tool": tool_name,
                "args": args,
                "attempts": len(attempts),
                "recovered_from_outage": len(attempts) > 1 and bool(res and res["ok"]),
                "initial_error": attempts[0]["response"]["error"] if len(attempts) > 1 and not attempts[0]["ok"] else None,
                "ok": bool(res and res["ok"]),
                "final_response": res,
                "record_ids_in_output": found_here,
            })

        decisive = [e["record_id"] for e in t["evidence"] if e["role"] == "decisive"]
        results.append({
            "workflow": entry["workflow"],
            "case_id": cid,
            "partition": part,
            "score": entry["score"],
            "reasons": entry["reasons"],
            "public_input": {
                "document_id": pub["document"]["document_id"],
                "path": f"data/partitions/{part}/{doc_rel}",
                "media_type": pub["document"]["media_type"],
                "attachments": [a["path"] for a in pub.get("attachments", [])],
                "excerpt": doc_text[:500] + ("..." if len(doc_text) > 500 else ""),
            },
            "example_walkthrough_steps": step_traces,
            "discovered_record_ids": sorted(discovered_ids),
            "decisive_evidence_covered": sorted(set(decisive) & discovered_ids),
            "evaluator_ground_truth": {
                "family_id": t["family_id"],
                "variant": t["variant"],
                "scenario_summary": t["scenario_summary"],
                "primary_category": t["routing"]["primary_category"],
                "labels": t["routing"]["labels"],
                "risk_level": t["risk_level"],
                "human_review_required": t["human_review_required"],
                "expected_outcome": t["expected_outcome"]["action"],
                "permitted_sensitive_actions": t["expected_outcome"]["permitted_sensitive_actions"],
                "evidence": t["evidence"],
                "valid_discovery_paths_count": sum(1 for p in t["discoverability"]["paths"] if not p.get("blocked")),
            },
        })

    return {
        "disclaimer": WALKTHROUGH_DISCLAIMER,
        "cases_replayed": len(results),
        "cases": results,
    }


def format_walkthrough(walk: dict) -> str:
    """Format a `run_walkthrough` result for terminal display."""
    lines = [
        "=" * 88,
        walk["disclaimer"],
        "=" * 88,
        "",
    ]
    for c in walk["cases"]:
        gt = c["evaluator_ground_truth"]
        inp = c["public_input"]
        lines.extend([
            f"### Showcase [{c['workflow']}] Case {c['case_id']} (partition: {c['partition']}, score: {c['score']})",
            f"Why selected: {', '.join(c['reasons'])}",
            f"Public input: {inp['path']} ({inp['media_type']})",
            "--- Input excerpt ---",
            inp["excerpt"].strip(),
            "---------------------",
            f"Presenter example path ({len(c['example_walkthrough_steps'])} steps; {gt['valid_discovery_paths_count']} valid paths exist in truth):",
        ])
        for st in c["example_walkthrough_steps"]:
            arg_str = ", ".join(f"{k}={v!r}" for k, v in st["args"].items())
            status = "OK" if st["ok"] else "ERROR"
            if st["recovered_from_outage"]:
                err = st["initial_error"]
                lines.append(
                    f"  Step {st['step']} (attempt 1): {st['tool']}({arg_str}) -> {err['code']} (retryable={err.get('retryable')})"
                )
                lines.append(
                    f"  Step {st['step']} (attempt {st['attempts']} retry): {st['tool']}({arg_str}) -> {status} "
                    f"(ids: {', '.join(st['record_ids_in_output']) or 'none'})"
                )
            else:
                lines.append(
                    f"  Step {st['step']}: {st['tool']}({arg_str}) -> {status} "
                    f"(ids: {', '.join(st['record_ids_in_output']) or 'none'})"
                )
        ev_str = ", ".join(f"{e['record_id']} ({e['role']}: {e['supports']})" for e in gt["evidence"])
        lines.extend([
            f"Evaluator truth summary: {gt['scenario_summary']}",
            f"Expected routing: primary={gt['primary_category']}, risk={gt['risk_level']}, human_review={gt['human_review_required']}",
            f"Expected outcome: {gt['expected_outcome']} (permitted sensitive: {gt['permitted_sensitive_actions'] or 'none'})",
            f"Ground-truth evidence: {ev_str}",
            f"Decisive evidence discovered by example path: {', '.join(c['decisive_evidence_covered'])}",
            "",
        ])
    return "\n".join(lines)
