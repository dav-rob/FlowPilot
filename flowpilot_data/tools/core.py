"""Enterprise environment loader (one partition only) and base tool session.

Security boundary: this package only reads `<partition_dir>/enterprise/*.jsonl` and `<partition_dir>/cases.jsonl`.
It never opens ground truth, which lives outside the data directory.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import re
from pathlib import Path
from typing import Any

from ..schema import SENSITIVE_TOOLS, SINGULAR, TABLES, TOOL_DOMAIN, TYPE_TO_TABLE
from ..util import read_jsonl
from .approvals import ApprovalAuthority, args_hash

ID_RE = re.compile(r"^[A-Z]{1,4}-[0-9A-F]{6,}$")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9@._\-]*")
HIDDEN_TABLES = {"service_status"}
SYSTEM_OF = {"supplier_fraud": "Supplier ERP / payments / fraud case management", "regulatory_compliance": "Policy repository / system inventory / audit management",
             "gdpr_data": "CRM / identity / data catalogue / legal holds", "it_asset": "CMDB / cloud inventory / deployments / ticketing",
             "contract_risk": "Contract repository / risk / financial controls / approvals"}


class ToolError(Exception):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


def tool(fn):
    fn._is_tool = True
    return fn


def _tokens(text: str) -> set[str]:
    out = set()
    for t in TOKEN_RE.findall(text.lower()):
        out.add(t)
        out.update(x for x in re.split(r"[@._\-]", t) if x)
    return out


class EnterpriseEnv:
    """Immutable view of one partition's enterprise records."""

    def __init__(self, partition_dir: str | Path):
        base = Path(partition_dir)
        self.partition_dir = base
        ent = base / "enterprise"
        if not ent.is_dir():
            raise FileNotFoundError(f"no enterprise directory under {base}")
        self.tables: dict[str, list[dict]] = {t: read_jsonl(ent / f"{t}.jsonl") for t in TABLES}
        self.index: dict[str, tuple[str, dict]] = {}
        for t, rows in self.tables.items():
            for r in rows:
                self.index[r["id"]] = (t, r)
        self.case_ids = {c["case_id"] for c in read_jsonl(base / "cases.jsonl")}
        self.links_out: dict[str, list[tuple[str, str]]] = {}
        self.links_in: dict[str, list[tuple[str, str]]] = {}
        self._token_index: dict[str, dict[str, set[str]]] = {}
        for t, rows in self.tables.items():
            if t in HIDDEN_TABLES:
                continue
            for r in rows:
                toks: dict[str, set[str]] = {}
                for k, v in r.items():
                    vals = v if isinstance(v, list) else [v]
                    for x in vals:
                        if isinstance(x, str) and ID_RE.match(x):
                            if x in self.index and k != "id":
                                self.links_out.setdefault(r["id"], []).append((k, x))
                                self.links_in.setdefault(x, []).append((k, r["id"]))
                            toks.setdefault(k, set()).add(x.lower())
                    if k in TABLES[t][1] or k == "id":
                        for x in vals:
                            if isinstance(x, (str, int)):
                                toks.setdefault(k, set()).update(_tokens(str(x)))
                self._token_index[r["id"]] = toks

    def get(self, rid: str) -> tuple[str, dict] | None:
        return self.index.get(rid)

    def rows(self, table: str) -> list[dict]:
        return self.tables[table]


class BaseSession:
    """Case-scoped tool session over one partition. All mutations are simulated and kept in memory."""

    def __init__(self, env: EnterpriseEnv, case_id: str, authority: ApprovalAuthority | None = None):
        if case_id not in env.case_ids:
            raise ValueError(f"case {case_id!r} is not part of partition {env.partition_dir.name!r}")
        self.env, self.case_id = env, case_id
        self.authority = authority or ApprovalAuthority()
        self.call_counts: dict[str, int] = {}
        self.state: dict[str, list[dict]] = {"review_cases": [], "tickets": [], "actions": [], "holds": [], "isolated": [], "approval_requests": []}
        self._outages = {r["tool"]: r for r in env.rows("service_status") if r.get("scope_case_id") == case_id}
        self._tools = {n: m for n, m in inspect.getmembers(self, predicate=inspect.ismethod) if getattr(m, "_is_tool", False)}

    # -- plumbing -----------------------------------------------------------
    def _rec(self, table: str, rid: Any, label: str | None = None) -> dict:
        if not isinstance(rid, str) or not rid.strip():
            raise ToolError("INVALID_ARGUMENT", f"{label or 'id'} must be a non-empty string")
        rid = rid.strip()
        hit = self.env.get(rid)
        if hit is None or hit[0] in HIDDEN_TABLES:
            raise ToolError("NOT_FOUND", f"No {SINGULAR[table]} record with id {rid!r} in this environment", searched=SINGULAR[table])
        if hit[0] != table:
            raise ToolError("WRONG_RECORD_TYPE", f"{rid} exists but is a {SINGULAR[hit[0]]}, not a {SINGULAR[table]}", record_type=SINGULAR[hit[0]])
        return copy.deepcopy(hit[1])

    def _where(self, table: str, **eq: Any) -> list[dict]:
        out = []
        for r in self.env.rows(table):
            if all(r.get(k) == v for k, v in eq.items()):
                out.append(copy.deepcopy(r))
        return out

    def _need(self, **kw: Any) -> None:
        for k, v in kw.items():
            if not isinstance(v, str) or not v.strip():
                raise ToolError("INVALID_ARGUMENT", f"{k} must be a non-empty string")

    def _require_approval(self, tool_name: str, args: dict, token: str | None) -> None:
        if not token:
            raise ToolError("APPROVAL_REQUIRED", f"{tool_name} is a sensitive ({SENSITIVE_TOOLS[tool_name]}) action and needs an explicit approval token; "
                            "use request_approval first and wait for a human decision", action=tool_name)
        ok, code = self.authority.verify_and_consume(token, self.case_id, tool_name, args)
        if not ok:
            raise ToolError(code, {"APPROVAL_INVALID": "Approval token is not valid", "APPROVAL_REUSED": "Approval token has already been used",
                                   "APPROVAL_WRONG_SCOPE": "Approval token was not issued for this case, tool and arguments"}[code], action=tool_name)

    # -- public API -----------------------------------------------------------
    def list_tool_names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, /, **kwargs: Any) -> dict:
        fn = self._tools.get(name)
        if fn is None:
            return {"ok": False, "tool": name, "error": {"code": "UNKNOWN_TOOL", "message": f"No such tool {name!r}", "available": self.list_tool_names()}}
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        sig = inspect.signature(fn)
        try:
            for k in kwargs:
                if k not in sig.parameters:
                    raise ToolError("INVALID_ARGUMENT", f"Unknown argument {k!r} for {name}", expected=list(sig.parameters))
            missing = [p for p, v in sig.parameters.items() if v.default is inspect._empty and p not in kwargs]
            if missing:
                raise ToolError("INVALID_ARGUMENT", f"Missing required argument(s): {', '.join(missing)}", expected=list(sig.parameters))
            out = self._outage(name)
            if out:
                raise out
            return {"ok": True, "tool": name, "data": fn(**kwargs)}
        except ToolError as e:
            return {"ok": False, "tool": name, "error": {"code": e.code, "message": e.message, **e.details}}

    async def acall(self, name: str, /, **kwargs: Any) -> dict:
        """Async-compatible entry point (e.g. for Flow4AI jobs); the backing store is in-memory so this never blocks."""
        await asyncio.sleep(0)
        return self.call(name, **kwargs)

    def _outage(self, name: str) -> ToolError | None:
        o = self._outages.get(name)
        if not o:
            return None
        n = self.call_counts[name]
        if o["mode"] == "down_for_first_n_calls" and n <= (o.get("n_failures") or 1):
            return ToolError("SERVICE_UNAVAILABLE", o["message"], retryable=True, retry_hint="transient; the service is expected to recover shortly")
        if o["mode"] == "down_with_alternate":
            return ToolError("SERVICE_UNAVAILABLE", o["message"], retryable=False, retry_hint="not expected to recover in this session; consider other systems that hold equivalent records")
        return None

    def catalogue(self) -> list[dict]:
        rows = []
        for n, fn in sorted(self._tools.items()):
            params = [{"name": p, "required": v.default is inspect._empty, "type": str(v.annotation).replace("typing.", "")}
                      for p, v in inspect.signature(fn).parameters.items() if p != "approval_token"]
            sens = SENSITIVE_TOOLS.get(n)
            rows.append({"name": n, "description": (fn.__doc__ or "").strip().split("\n")[0], "parameters": params,
                         "system": SYSTEM_OF.get(TOOL_DOMAIN.get(n, ""), "Cross-system utilities"),
                         "side_effects": "simulated_state_change" if sens or n in ("create_review_case", "create_ticket", "request_approval") else "none",
                         "requires_approval": bool(sens), **({"approval_class": sens} if sens else {})})
        return rows

    # -- generic tools ----------------------------------------------------------
    @tool
    def list_tools(self) -> dict:
        """List available tools with parameter schemas and side-effect/approval requirements."""
        return {"tools": self.catalogue()}

    def _preview(self, rid: str) -> dict:
        t, r = self.env.index[rid]
        keys = [k for k in ("name", "title", "full_name", "hostname", "invoice_number", "po_number", "contract_number", "summary", "subject", "status", "rating", "tool") if k in r]
        return {"id": rid, "record_type": SINGULAR[t], **{k: r[k] for k in keys[:4]}}

    @tool
    def search_records(self, query: str, record_types: list | None = None, limit: int = 8) -> dict:
        """Free-text enterprise search across systems (names, references, ids, emails). Returns previews only."""
        self._need(query=query)
        if not isinstance(limit, int) or not 1 <= limit <= 25:
            raise ToolError("INVALID_ARGUMENT", "limit must be an integer between 1 and 25")
        allowed = None
        if record_types:
            bad = [x for x in record_types if x not in TYPE_TO_TABLE or TYPE_TO_TABLE[x] in HIDDEN_TABLES]
            if bad:
                raise ToolError("INVALID_ARGUMENT", f"unknown record_types {bad}", valid=sorted(x for x in TYPE_TO_TABLE if TYPE_TO_TABLE[x] not in HIDDEN_TABLES))
            allowed = {TYPE_TO_TABLE[x] for x in record_types}
        q = _tokens(query)
        hits = []
        for rid, toks in self.env._token_index.items():
            if allowed and self.env.index[rid][0] not in allowed:
                continue
            matched = {f for f, vs in toks.items() if q & vs}
            score = len(q & set().union(*toks.values())) if toks else 0
            if score:
                hits.append((-score, rid, sorted(matched)))
        hits.sort()
        if not hits:
            raise ToolError("NOT_FOUND", f"No records match {query!r}")
        return {"query": query, "total_matches": len(hits), "truncated": len(hits) > limit,
                "results": [{**self._preview(rid), "matched_fields": m} for _, rid, m in hits[:limit]]}

    @tool
    def get_linked_records(self, record_id: str) -> dict:
        """Traverse evidence links: ids and types of records that reference, or are referenced by, a record."""
        self._need(record_id=record_id)
        record_id = record_id.strip()
        hit = self.env.get(record_id)
        if hit is None or hit[0] in HIDDEN_TABLES:
            raise ToolError("NOT_FOUND", f"No record {record_id!r}")
        out = [{"direction": "outgoing", "relation": rel, **self._preview(t)} for rel, t in self.env.links_out.get(record_id, [])]
        out += [{"direction": "incoming", "relation": rel, **self._preview(t)} for rel, t in self.env.links_in.get(record_id, [])]
        return {"record_id": record_id, "record_type": SINGULAR[hit[0]], "links": out}

    @tool
    def get_audit_trail(self, record_id: str) -> dict:
        """Read the system audit log entries recorded against any record id."""
        self._need(record_id=record_id)
        record_id = record_id.strip()
        hit = self.env.get(record_id)
        if hit is None or hit[0] in HIDDEN_TABLES:
            raise ToolError("NOT_FOUND", f"No record {record_id!r}")
        rows = sorted(self._where("audit_log", subject_id=record_id), key=lambda r: r["timestamp"], reverse=True)
        return {"record_id": record_id, "entries": rows}

    @tool
    def create_review_case(self, case_type: str, evidence: list, summary: str = "", priority: str = "normal") -> dict:
        """Open a simulated review case (fraud, audit, data_protection, it_security, contract or other) citing evidence record ids."""
        if case_type not in ("fraud", "audit", "data_protection", "it_security", "contract", "other"):
            raise ToolError("INVALID_ARGUMENT", "case_type must be one of fraud, audit, data_protection, it_security, contract, other")
        if not isinstance(evidence, list) or not evidence:
            raise ToolError("INVALID_ARGUMENT", "evidence must be a non-empty list of record ids or {record_id, note} objects")
        ids = [e.get("record_id") if isinstance(e, dict) else e for e in evidence]
        unknown = [i for i in ids if not isinstance(i, str) or self.env.get(i) is None or self.env.get(i)[0] in HIDDEN_TABLES]
        if unknown:
            raise ToolError("INVALID_EVIDENCE", "Evidence must cite existing records", unknown_ids=[str(u) for u in unknown])
        rid = f"RVW-{self.case_id[-6:]}-{len(self.state['review_cases']) + 1:02d}"
        rec = {"review_case_id": rid, "case_type": case_type, "evidence_ids": ids, "summary": summary, "priority": priority, "simulated": True}
        self.state["review_cases"].append(rec)
        return rec

    @tool
    def create_ticket(self, summary: str, category: str = "general", related_records: list | None = None) -> dict:
        """Create a simulated service ticket (no sensitive effect)."""
        self._need(summary=summary)
        rel = related_records or []
        unknown = [i for i in rel if not isinstance(i, str) or self.env.get(i) is None or self.env.get(i)[0] in HIDDEN_TABLES]
        if unknown:
            raise ToolError("INVALID_EVIDENCE", "related_records must exist", unknown_ids=[str(u) for u in unknown])
        rec = {"ticket_id": f"SIM-TKT-{len(self.state['tickets']) + 1:03d}", "summary": summary, "category": category, "related_records": rel, "simulated": True}
        self.state["tickets"].append(rec)
        return rec

    @tool
    def request_approval(self, action: str, arguments: dict, justification: str) -> dict:
        """Ask a human approver to authorise a sensitive action. Returns a pending request; an approval token is only issued by the approver."""
        if action not in SENSITIVE_TOOLS:
            raise ToolError("INVALID_ARGUMENT", "action must be a sensitive tool", sensitive_tools=sorted(SENSITIVE_TOOLS))
        if not isinstance(arguments, dict):
            raise ToolError("INVALID_ARGUMENT", "arguments must be an object")
        self._need(justification=justification)
        args = {k: v for k, v in arguments.items() if k != "approval_token"}
        req = self.authority.submit(self.case_id, action, args, justification)
        self.state["approval_requests"].append({k: req[k] for k in ("request_id", "tool", "args_hash")})
        out = {"request_id": req["request_id"], "status": req["status"], "action": action, "arguments": args}
        if req["status"] == "approved":
            out["approval_token"] = req.get("token")
        return out

    def _sensitive(self, name: str, args: dict, token: str | None, effect: dict) -> dict:
        self._require_approval(name, args, token)
        rec = {"action": name, "arguments": args, "simulated": True, **effect}
        self.state["actions"].append(rec)
        return rec
