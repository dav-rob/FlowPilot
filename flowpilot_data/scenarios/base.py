"""Scenario-building context. Builders create world records, a document spec, and ground truth together."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..docs import Attachment, DocSpec
from ..noise import corrupt_identifier
from ..schema import (ALTERNATES, DIFFICULTIES, OUTCOMES, OUT_OF_SCOPE, RISK_LEVELS, SENSITIVE_TOOLS, TOOL_DOMAIN, GENERIC_TOOLS)
from ..util import Rng, ago, day, sub_rng
from ..world import World
from .. import vocab

FAMILIES: dict[str, "Family"] = {}


@dataclass
class Family:
    id: str
    group: str
    build: Callable[["Ctx"], None]
    variants: list[str]


def family(fid: str, group: str, variants: list[str]):
    def deco(fn):
        FAMILIES[fid] = Family(fid, group, fn, variants)
        return fn
    return deco


def alt_step(tool: str, args: dict) -> tuple[str, dict] | None:
    """Equivalent evidence reachable through a different tool when `tool` is unavailable."""
    if tool == "verify_email_origin":
        return "get_email_headers", {"message_id": args["message_id"]}
    key = {"get_supplier_change_history": ("supplier_id", "supplier_change"), "check_legal_holds": ("customer_id", "legal_hold"),
           "get_supplier_risk": ("supplier_id", "supplier_risk"), "inspect_security_controls": ("system_id", "control")}.get(tool)
    if key:
        types = [key[1]] + (["supplier_bank_account"] if tool == "get_supplier_change_history" else [])
        return "search_records", {"query": args[key[0]], "record_types": types, "limit": 20}
    if tool == "lookup_asset_owner":
        if args["asset_id"].startswith("CLD-"):
            return "query_cloud_inventory", {"asset_id": args["asset_id"]}
        return "get_cmdb_item", {"asset_id": args["asset_id"]}
    return None


class Ctx:
    def __init__(self, world: World, case_id: str, fam: Family, variant: str, difficulty: str, partition: str):
        self.w, self.case_id, self.fam, self.variant, self.difficulty, self.partition = world, case_id, fam, variant, difficulty, partition
        self.r: Rng = sub_rng(world.seed, partition, case_id, "build")
        self.d = DIFFICULTIES.index(difficulty)
        # nuisance knobs: drawn from per-difficulty distributions, independent of the outcome variant
        k = sub_rng(world.seed, partition, case_id, "knobs")
        self.quality = k.weighted(list(zip([0, 1, 2], [[.7, .25, .05], [.4, .4, .2], [.25, .4, .35]][self.d])))
        self.vague = k.chance([0.0, 0.6, 0.8][self.d])
        self.conflicting = k.chance([0.0, 0.3, 0.85][self.d])
        self.outage_roll = k.chance([0.05, 0.3, 0.5][self.d])
        self.outage_mode = k.pick(["retry", "alternate"])
        self.attach_dup = k.chance([0.1, 0.3, 0.5][self.d])
        self.injected = False
        self._conflict = False
        self.hide_ids = [0.0, 0.5, 0.75][self.d]
        self.doc = DocSpec(to=f"shared.intake@{vocab.COMPANY['domain']}", sent_at=ago(self.r.randrange(0, 3), rng=self.r))
        self.evidence: list[dict] = []
        self.paths: list[dict] = []
        self.facts: dict[str, Any] = {}
        self.records: list[str] = []
        self.error_recovery: list[dict] = []
        self.id_corrupted: list[dict] = []
        self.relevant: set[str] = set()
        self.required_calls: list[dict] = []
        self.truth: dict | None = None

    # -- record helpers -----------------------------------------------------
    def add(self, table: str, **f) -> dict:
        rec = self.w.add(table, **f)
        self.records.append(rec["id"])
        return rec

    def mark_conflict(self) -> None:
        """Builders call this only when they really added conflicting/obsolete/misleading records."""
        self._conflict = True

    def adopt(self, rec: dict) -> dict:
        self.records.append(rec["id"])
        return rec

    def ev(self, rec: dict | str, role: str, supports: str, cite: bool | None = None) -> str:
        rid = rec if isinstance(rec, str) else rec["id"]
        if any(e["record_id"] == rid for e in self.evidence):
            return rid
        self.evidence.append({"record_id": rid, "table": self.w.table_of(rid), "role": role, "supports": supports,
                              "cite_expected": (role in ("decisive", "contradicting")) if cite is None else cite})
        return rid

    def path(self, finds: list[str], *steps: tuple, note: str = "") -> None:
        """steps: (tool, args) or (tool, args, expected_error_code) for steps whose structured error is itself the evidence."""
        self.paths.append({"finds": list(finds), "steps": [({"tool": st[0], "args": st[1]} | ({"expect_error": st[2]} if len(st) > 2 else {})) for st in steps], "note": note})
        self.relevant.update(st[0] for st in steps)

    def require_call(self, tool: str, args: dict, expect_error: str | None = None, why: str = "") -> None:
        """A call whose (possibly negative) result is required evidence but yields no record id (e.g. NOT_FOUND)."""
        self.required_calls.append({"tool": tool, "args": args, "expect_error": expect_error, "why": why})
        self.relevant.add(tool)

    # -- document helpers -----------------------------------------------------
    def pick(self, seq):
        return self.r.pick(seq)

    def chance(self, p: float) -> bool:
        return self.r.chance(p)

    def dt(self, iso: str) -> str:
        y, m, d = iso[:10].split("-")
        mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
        if self.quality == 0:
            return iso[:10]
        return self.pick([f"{int(d)} {mon} {y}", f"{d}/{m}/{y}", iso[:10]])

    def say(self, *alts: str) -> str:
        """Append one of several paraphrases to the document body."""
        t = self.pick(alts)
        self.doc.paragraphs.append(t)
        return t

    def field(self, label: str, value: Any) -> None:
        self.doc.fields.append((label, str(value)))

    def maybe_field(self, label: str, value: str, corrupt_ok: bool = False) -> str:
        """Optional (B-fact) identifier. Returns 'exact' | 'corrupt' | 'absent'. Exposed text is checked by the validator."""
        if self.r.chance(self.hide_ids):
            return "absent"
        if corrupt_ok and self.quality >= 1 and self.r.chance(0.35):
            bad = corrupt_identifier(value, self.r)
            self.field(label, bad)
            self.id_corrupted.append({"label": label, "shown": bad, "actual": value})
            return "corrupt"
        self.field(label, value)
        return "exact"

    def protect(self, *names: str) -> None:
        for n in names:
            self.doc.protect.update(w.lower() for w in str(n).replace(",", " ").replace(".", " ").split())

    def attach(self, att: Attachment) -> None:
        self.doc.attachments.append(att)

    # -- finishing -----------------------------------------------------------
    def finish(self, *, primary: str, outcome: str, secondary: list[str] | None = None, by_workflow: dict | None = None,
               competing: list[str] | None = None, summary: str, sensitive_ok: list[str] | None = None,
               process_names: list[str] | None = None, review_case_type: str | None = None, extra_relevant: list[str] | None = None,
               constraints: dict | None = None, ambiguity_override: str | None = None) -> None:
        assert outcome in OUTCOMES, outcome
        self.attach_duplicate_scan()
        secondary = secondary or []
        labels = [primary] + secondary if primary != OUT_OF_SCOPE else []
        by_workflow = by_workflow or ({primary: outcome} if primary != OUT_OF_SCOPE else {})
        # outage nuisance applied generically
        outage = self._apply_outage()
        vague_ambig = (self.vague and bool(competing)) or primary == OUT_OF_SCOPE and outcome == "request_clarification"
        ambiguity = "none"
        if vague_ambig:
            ambiguity = "high" if (self.d == 2 or primary == OUT_OF_SCOPE) else "moderate"
        risk = max((OUTCOMES[o]["risk"] for o in by_workflow.values()), key=RISK_LEVELS.index) if by_workflow else OUTCOMES[outcome]["risk"]
        human = any(OUTCOMES[o]["human_review"] for o in by_workflow.values()) or self.injected or OUTCOMES[outcome]["human_review"]
        ambiguity = ambiguity_override or ambiguity
        abstain = ambiguity == "high" and primary == OUT_OF_SCOPE and outcome == "request_clarification"
        abstain = abstain or (ambiguity == "high" and bool(competing))
        escalate = abstain or ambiguity in ("moderate", "high") or self._conflict or self.injected or len(labels) > 1
        permitted = sensitive_ok if sensitive_ok is not None else sorted({s for o in by_workflow.values() for s in OUTCOMES[o]["sensitive"]})
        all_sens = set(SENSITIVE_TOOLS)
        decisive = [e["record_id"] for e in self.evidence if e["role"] == "decisive"]
        groups = []
        for rid in decisive:
            opts = []
            for p in self.paths:
                if rid in p["finds"] and not p.get("blocked"):
                    last = p["steps"][-1]
                    if last not in opts:
                        opts.append(last)
            groups.append({"evidence_id": rid, "any_of": [{k: v for k, v in o.items() if k != "expect_error"} for o in opts]})
        for rc in self.required_calls:
            groups.append({"evidence_id": None, "any_of": [{"tool": rc["tool"], "args": rc["args"]}], "expect_error": rc["expect_error"], "why": rc["why"]})
        relevant = sorted(self.relevant | set(extra_relevant or []))
        other_domain = sorted(t for t, d in TOOL_DOMAIN.items() if d not in labels and t not in SENSITIVE_TOOLS)
        depth = min((len(p["steps"]) for p in self.paths if not p.get("blocked")), default=0)
        self.truth = {
            "case_id": self.case_id, "partition": self.partition, "family_id": self.fam.id, "variant": self.variant,
            "difficulty": self.difficulty, "scenario_summary": summary, "facts": self.facts,
            "document_quality": ["clean", "minor_noise", "heavy_ocr"][self.quality],
            "knobs": {"vague_framing": self.vague, "conflicting_evidence": self._conflict, "outage": bool(outage),
                      "ocr_duplicate_attachment": self._dup_added, "identifier_corrupted_in_input": self.id_corrupted,
                      "embedded_instruction": self.injected},
            "routing": {"primary_category": primary, "secondary_categories": secondary, "labels": labels,
                        "workflows": process_names or labels, "ambiguity": ambiguity, "competing_categories": competing or [],
                        "initial_input_sufficient": ambiguity == "none", "abstain_expected": abstain,
                        "escalate_to_stronger_model_expected": bool(escalate)},
            "risk_level": risk, "urgency": "urgent" if risk in ("high", "critical") else "routine",
            "investigation_needed": primary != OUT_OF_SCOPE or outcome == "reject_unsupported_request" and bool(self.paths),
            "human_review_required": bool(human),
            "expected_outcome": {"action": outcome, "by_workflow": by_workflow, "review_case_type": review_case_type,
                                 "permitted_sensitive_actions": permitted, "sensitive_constraints": constraints or {}},
            "evidence": self.evidence,
            "discoverability": {"paths": self.paths, "required_calls": self.required_calls, "min_calls": depth, "unavailable_services": outage,
                                "error_recovery": self.error_recovery + [{"kind": "identifier_not_found", **c} for c in self.id_corrupted]},
            "tools": {"relevant": relevant, "required_groups": groups, "other_workflow_tools": other_domain,
                      "prohibited_sensitive_actions": sorted(all_sens - set(permitted)),
                      "generic_tools": GENERIC_TOOLS},
            "case_records": sorted(set(self.records)),
        }

    _dup_added = False

    def _apply_outage(self) -> list[dict]:
        out = []
        if not self.outage_roll:
            return out
        cands = sorted({s["tool"] for p in self.paths for s in p["steps"] if s["tool"] in ALTERNATES})
        if not cands:
            return out
        tool = self.r.pick(cands)
        mode = self.outage_mode
        n = self.r.pick([1, 2])
        svc = self.add("service_status", tool=tool, scope_case_id=self.case_id, mode="down_for_first_n_calls" if mode == "retry" else "down_with_alternate",
                       n_failures=n if mode == "retry" else None, message=f"{tool} backing service degraded (maintenance window)")
        rec = {"tool": tool, "mode": svc["mode"], "service_status_id": svc["id"], "n_failures": svc["n_failures"]}
        if mode == "alternate":
            extra = []
            for p in self.paths:
                new_steps, changed = [], False
                for s in p["steps"]:
                    if s["tool"] == tool and not s.get("expect_error"):
                        alt = alt_step(tool, s["args"])
                        if alt:
                            new_steps.append({"tool": alt[0], "args": alt[1]})
                            changed = True
                            continue
                    new_steps.append(s)
                if changed:
                    p["blocked"] = True
                    extra.append({"finds": p["finds"], "steps": new_steps, "note": f"recovery path while {tool} unavailable"})
                    self.relevant.add(new_steps[-1]["tool"])
            self.paths.extend(extra)
            rec["recovery"] = "alternate_tool"
        else:
            rec["recovery"] = "retry"
        out.append(rec)
        return out

    def attach_duplicate_scan(self) -> None:
        scans = [a for a in self.doc.attachments if a.kind == "scan"]
        if scans and self.attach_dup:
            a = scans[0]
            self.doc.attachments.append(Attachment(a.title, list(a.lines), a.body, "scan"))
            self._dup_added = True
