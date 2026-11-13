"""Evaluator-only access to hidden labels; never imported by the investigation engine."""

import asyncio
import uuid
from collections import Counter
from flowpilot_data.evaluate import evaluate, score_case, load_truth
from .store import now
from .catalog import case_list
from .assurance import RULESET_VERSION
from .version import application_revision


def prediction(run):
    c = run.get("classification") or {}
    o = run.get("outcome") or {}
    m = run["metrics"]
    trace = []
    artifact_ids = set()
    for event in run["events"]:
        if event["kind"] == "tool_result" and event.get("result", {}).get("ok"):
            data = event["result"].get("data", {})
            for key in ("review_case_id", "ticket_id", "request_id"):
                if data.get(key):
                    artifact_ids.add(data[key])
    for e in run["events"]:
        if e["kind"] != "tool_result":
            continue
        result = e.get("result", {})
        error = result.get("error", {})
        trace.append(
            {
                "tool": e["tool"],
                "arguments": e.get("arguments", {}),
                "ok": result.get("ok", False),
                "error_code": error.get("code"),
                "latency_ms": e.get("duration_ms"),
            }
        )
    return {
        "case_id": run["case_id"],
        "system": run["mode"],
        "routing": {
            "primary_category": c.get("primary"),
            "secondary_categories": [
                x for x in c.get("categories", []) if x != c.get("primary")
            ],
            "abstained": c.get("primary") == "out_of_scope",
            "escalated": any(e["kind"] == "escalation" for e in run["events"]),
            "needs_investigation": bool(trace),
            "risk_level": o.get("risk", c.get("risk")),
            "confidence": c.get("confidence"),
        },
        "outcome": {
            "action": o.get("outcome_code"),
            "by_workflow": o.get("by_workflow", {}),
            "cited_evidence": [
                e["record_id"]
                for e in o.get("evidence", [])
                if e["record_id"] not in artifact_ids
            ],
            "executed_sensitive_actions": [
                a["tool"] for a in run.get("approvals", []) if a["status"] == "executed"
            ],
        },
        "tool_trace": trace,
        "usage": {**m.get("usage", {}), "latency_ms": run["duration_ms"]},
        "demo_fixture": run["mode"] != "live",
    }


class Evaluator:
    def __init__(self, store, engine):
        self.store = store
        self.engine = engine
        self.tasks = {}

    def create(self, partition, limit, mode):
        obj = {
            "id": uuid.uuid4().hex,
            "status": "queued",
            "mode": mode,
            "partition": partition,
            "ruleset_version": RULESET_VERSION,
            "application_revision": application_revision(),
            "created_at": now(),
            "completed": 0,
            "total": limit,
            "metrics": {},
            "results": [],
            "warning": (
                "Deterministic simulation. These metrics do not measure live model performance."
                if mode == "simulation"
                else "Live classifier and tool-calling performance on synthetic cases. Ground truth is isolated from the agent."
            ),
        }
        self.store.put("evaluation", obj)
        task = asyncio.create_task(self.execute(obj))
        self.tasks[obj["id"]] = task
        task.add_done_callback(lambda _: self.tasks.pop(obj["id"], None))
        return obj

    def score_saved(self, partition="train"):
        """New analysis of the latest saved AI attempt per labelled document.

        Original executions and their versions remain unchanged; no model or tool
        is invoked and the current expected answers are used only here.
        """
        truth_map = {t["case_id"]: t for t in load_truth(self.engine.root, partition)}
        selected = {}
        for run in self.store.list("run"):
            if (
                run.get("mode") == "live"
                and run.get("partition") == partition
                and run.get("status") not in ("queued", "running")
                and run.get("purpose", "business") == "business"
                and run.get("case_id") in truth_map
            ):
                selected.setdefault(run["case_id"], run)
        if not selected:
            raise ValueError(
                "No saved AI reviews with expected answers are available in this partition"
            )
        runs = list(selected.values())
        predictions = [prediction(run) for run in runs]
        report = evaluate(
            [truth_map[r["case_id"]] for r in runs], predictions, include_cases=False
        )
        results = []
        for run, pred in zip(runs, predictions):
            truth = truth_map[run["case_id"]]
            scores = score_case(truth, pred)
            results.append(
                {
                    "case_id": run["case_id"],
                    "run_id": run["id"],
                    "title": run["title"],
                    "status": run["status"],
                    "primary": (run.get("classification") or {}).get("primary"),
                    "outcome_code": (run.get("outcome") or {}).get("outcome_code"),
                    "expected_outcome": truth["expected_outcome"]["action"],
                    "actual_outcome": (run.get("outcome") or {}).get("outcome_code"),
                    "expected_categories": truth["routing"]["labels"],
                    "actual_categories": (run.get("classification") or {}).get(
                        "categories", []
                    ),
                    "models": run["metrics"].get("providers", []),
                    "ruleset_version": run.get("ruleset_version"),
                    "application_revision": run.get("application_revision"),
                    "primary_correct": scores["primary_correct"],
                    "outcome_correct": scores["outcome_correct"],
                    "grounded_correct": scores["grounded_correct"],
                    "tool_calls": scores["calls"],
                    "required_groups_satisfied": scores["groups_satisfied"],
                    "required_groups_total": scores["groups_total"],
                    "duration_ms": run["duration_ms"],
                    "review_created_at": run["created_at"],
                    "error": run.get("error"),
                }
            )
        obj = {
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "finished_at": now(),
            "status": "completed",
            "mode": "live",
            "partition": partition,
            "source": "saved_ai_reviews",
            "new_model_calls": 0,
            "completed": len(runs),
            "total": len(runs),
            "results": results,
            "ruleset_version": RULESET_VERSION,
            "application_revision": application_revision(),
            "metrics": report["metrics"],
            "coverage": report["coverage"],
            "strata": report["strata"],
            "warning": "Analysis of the latest saved AI attempt for each labelled document, using current expected answers. No new AI or business-tool calls. Timings and usage describe the original reviews; this selected development sample is not a held-out benchmark.",
        }
        self.store.put("evaluation", obj)
        return obj

    async def execute(self, obj):
        try:
            obj["status"] = "running"
            self.store.put("evaluation", obj)
            # Selection is independent of hidden labels: curated public cases first on train.
            cases = case_list(obj["partition"], self.engine.root)[: obj["total"]]
            truths = load_truth(self.engine.root, obj["partition"])
            truth_map = {t["case_id"]: t for t in truths}
            selected = {c["case_id"] for c in cases}
            truths = [t for t in truths if t["case_id"] in selected]
            preds = []
            providers = Counter()
            blocks = 0
            failed = 0
            model_calls = 0
            for case in cases:
                run = self.engine.create(
                    case_id=case["case_id"],
                    partition=obj["partition"],
                    document=case["document"],
                    mode=obj["mode"],
                    title=case["title"],
                    purpose="evaluation",
                )
                # Register evaluation-owned runs so approvals are locked until investigation completion.
                task = asyncio.create_task(self.engine.execute(run["id"]))
                self.engine.tasks[run["id"]] = task
                try:
                    await task
                finally:
                    self.engine.tasks.pop(run["id"], None)
                run = self.store.get("run", run["id"])
                pred = prediction(run)
                preds.append(pred)
                scores = score_case(truth_map[case["case_id"]], pred)
                failed += run["status"] == "failed"
                blocks += run["metrics"]["unsafe_actions_blocked"]
                model_calls += run["metrics"]["model_calls"]
                providers.update(run["metrics"]["providers"])
                obj["results"].append(
                    {
                        "case_id": case["case_id"],
                        "run_id": run["id"],
                        "title": case["title"],
                        "status": run["status"],
                        "primary": (run.get("classification") or {}).get("primary"),
                        "outcome_code": (run.get("outcome") or {}).get("outcome_code"),
                        "expected_outcome": truth_map[case["case_id"]][
                            "expected_outcome"
                        ]["action"],
                        "actual_outcome": (run.get("outcome") or {}).get(
                            "outcome_code"
                        ),
                        "expected_categories": truth_map[case["case_id"]]["routing"][
                            "labels"
                        ],
                        "actual_categories": (run.get("classification") or {}).get(
                            "categories", []
                        ),
                        "models": run["metrics"].get("providers", []),
                        "requires_approval": bool(
                            (run.get("outcome") or {}).get("requires_approval")
                        ),
                        "ruleset_version": run.get("ruleset_version"),
                        "application_revision": run.get("application_revision"),
                        "primary_correct": scores["primary_correct"],
                        "outcome_correct": scores["outcome_correct"],
                        "grounded_correct": scores["grounded_correct"],
                        "tool_calls": scores["calls"],
                        "required_groups_satisfied": scores["groups_satisfied"],
                        "required_groups_total": scores["groups_total"],
                        "duration_ms": run["duration_ms"],
                        "error": run.get("error"),
                    }
                )
                report = evaluate(truths, preds, include_cases=False)
                obj.update(
                    completed=len(preds),
                    metrics=report["metrics"],
                    coverage=report["coverage"],
                    strata=report["strata"],
                )
                obj["metrics"]["runtime"] = {
                    "providers": dict(providers),
                    "model_calls": model_calls,
                    "unsafe_actions_blocked": blocks,
                    "failed_runs": failed,
                }
                self.store.put("evaluation", obj)
            obj["status"] = "completed"
            obj["finished_at"] = now()
            self.store.put("evaluation", obj)
        except asyncio.CancelledError:
            obj["status"] = "failed"
            obj["error"] = "Application stopped during evaluation."
            self.store.put("evaluation", obj)
        except Exception as e:
            obj["status"] = "failed"
            obj["error"] = f"{type(e).__name__}: {str(e)[:500]}"
            self.store.put("evaluation", obj)
