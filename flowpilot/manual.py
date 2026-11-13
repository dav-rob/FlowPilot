"""Human review work items and explicit business routes, separate from AI execution."""

from copy import deepcopy
import uuid
from .store import now
from .version import application_revision

ACTION_DEPARTMENTS = {
    "place_payment_hold": "Finance",
    "release_payment": "Finance",
    "update_supplier_bank_details": "Finance",
    "execute_erasure": "Privacy",
    "export_customer_data": "Privacy",
    "update_customer_record": "Customer operations",
    "isolate_asset": "Security",
    "revoke_access_grant": "Security",
    "decommission_asset": "IT operations",
    "release_contract_for_signature": "Legal",
}


def create_reviews(run, *, migrated=False):
    """Materialise explicit outcome handoffs, never inferred from document keywords.

    Older reports may be enrolled, but keep their original execution/versions intact.
    Informational department recommendations alone never create an approval gate.
    """
    if "manual_reviews" in run or run.get("mode") == "replay":
        return False
    outcome = run.get("outcome") or {}
    if not outcome or run.get("status") not in ("completed", "awaiting_approval"):
        return False
    code = outcome.get("outcome_code")
    codes = {code, *(outcome.get("by_workflow") or {}).values()}
    departments = outcome.get("departments") or []
    specs = []
    if "block_pending_privacy_assessment" in codes:
        specs = [
            (
                "Privacy",
                "Privacy assessment",
                "The proposed contract or data-processing change",
                "A privacy decision is required before the proposed change can proceed.",
            )
        ]
    if "escalate_to_senior_approval" in codes:
        specs += [
            (
                "Legal & senior management",
                "Senior contract review",
                "The proposed acceptance of the contract issue",
                "Record the senior/legal decision; this does not grant retrospective approval or amend the contract.",
            )
        ]
    if "route_for_standard_approval" in codes and not specs:
        allowed = {
            "finance": "Finance",
            "legal": "Legal",
            "privacy": "Privacy",
            "security": "Security",
        }
        owners = list(
            dict.fromkeys(
                allowed[d.lower()] for d in departments if d.lower() in allowed
            )
        ) or ["Contract owner"]
        specs = [
            (
                d,
                f"{d} contract review",
                "The proposed contract change",
                "All requested departmental reviews must be recorded before this handoff is complete.",
            )
            for d in owners
        ]
    if "refer_to_security_review" in codes:
        specs += [
            (
                "Security",
                "Security review",
                "The flagged request",
                "A security reviewer must decide the next step; no customer or access changes are executed by this decision.",
            )
        ]
    if codes.intersection({"manual_review", "request_owner_attestation"}) and not specs:
        owner = str(departments[0])[:100] if departments else "Business owner"
        specs = [
            (
                owner,
                "Business review",
                "The decision on this request",
                "Review the findings and record whether the request may proceed.",
            )
        ]
    if outcome.get("requires_approval") and not run.get("approvals") and not specs:
        owner = str(departments[0])[:100] if departments else "Business owner"
        specs = [
            (
                owner,
                "Business approval",
                "The proposed next step",
                "Record the business decision. This approval does not execute a change.",
            )
        ]
    run["manual_reviews"] = [
        {
            "request_id": "REV-" + uuid.uuid4().hex[:10].upper(),
            "department": d,
            "title": title,
            "hold_scope": scope,
            "next_step": step,
            "reason": outcome.get("conclusion") or outcome.get("summary", ""),
            "status": "pending",
            "created_at": now(),
            "origin": "enrolled_from_saved_findings" if migrated else "outcome_handoff",
            "workflow_revision": "2026-11-13.1",
            "application_revision": application_revision(),
        }
        for d, title, scope, step in specs
    ]
    if specs:
        run["status"] = "awaiting_approval"
        outcome["requires_approval"] = True
    return bool(specs)


def pending(run):
    return any(
        x.get("status") == "pending"
        for x in run.get("approvals", []) + run.get("manual_reviews", [])
    )


def route(run):
    reviews = run.get("manual_reviews", [])
    actions = run.get("approvals", [])
    if run.get("mode") == "replay":
        return {
            "path": "recording",
            "label": "Saved example",
            "detail": "Read-only recording. No new review or action is performed.",
        }
    if run.get("status") in ("queued", "running"):
        return {
            "path": "in_progress",
            "label": "In progress",
            "detail": "AI Review checks the evidence and selects the next step.",
        }
    if run.get("status") in ("failed", "cancelled"):
        return {
            "path": "attention",
            "label": "Review incomplete",
            "detail": "A person needs to review the available findings. Pending changes cannot be approved.",
        }
    if any(x.get("status") == "denied" for x in reviews + actions):
        return {
            "path": "declined",
            "label": "Human decision: declined",
            "detail": "A required approval was declined. The declined proposal has not been applied.",
        }
    if any(x.get("status") == "failed" for x in actions):
        return {
            "path": "blocked",
            "label": "Proposed action could not proceed",
            "detail": "The approved proposal failed its execution checks. Review the recorded restriction or error.",
        }
    if (run.get("outcome") or {}).get("outcome_code") == "refuse_erasure_legal_hold":
        return {
            "path": "blocked",
            "label": "Deletion prohibited",
            "detail": "The findings identify an active legal hold. Approval cannot authorise deletion of protected records.",
        }
    if pending(run):
        return {
            "path": "human_review",
            "label": "Held for human review",
            "detail": "The proposed next step is paused. Reviewers must decide the requests in Approvals.",
        }
    if reviews or actions:
        return {
            "path": "human_complete",
            "label": "Human review complete",
            "detail": "Decisions are recorded. Departmental approval alone makes no business change; only explicitly approved actions are simulated.",
        }
    return {
        "path": "default",
        "label": "Standard route complete",
        "detail": "Checks and findings are complete. No approval workflow was opened and no consequential change was applied automatically.",
    }


def work_items(run, *, busy=False):
    if run.get("mode") == "replay":
        return []
    ready = run.get("status") in ("completed", "awaiting_approval") and not busy
    department_block = any(
        x.get("status") != "approved" for x in run.get("manual_reviews", [])
    )
    items = []
    for kind, rows in (
        ("action_approval", run.get("approvals", [])),
        ("department_review", run.get("manual_reviews", [])),
    ):
        for row in rows:
            blocked = ""
            if not ready:
                blocked = "The AI Review must finish successfully before a decision can be recorded."
            elif kind == "action_approval" and department_block:
                blocked = "Required departmental reviews must be approved before this change can be applied."
            item = {
                "id": run["id"] + ":" + row["request_id"],
                "run_id": run["id"],
                "request_id": row["request_id"],
                "kind": kind,
                "title": row.get("title")
                or row.get("tool", "Proposed change").replace("_", " ").capitalize(),
                "case_title": run.get("title", "Document review"),
                "department": row.get("department")
                or ACTION_DEPARTMENTS.get(row.get("tool"), "Business owner"),
                "reason": row.get("reason", row.get("justification", "")),
                "hold_scope": row.get(
                    "hold_scope",
                    "Only the proposed change is paused; it has not been applied.",
                ),
                "next_step": row.get(
                    "next_step",
                    "Approve to apply this specific change to fictional records, or decline to leave it unapplied.",
                ),
                "status": (
                    "blocked"
                    if row["status"] == "pending"
                    and run.get("status") in ("failed", "cancelled")
                    else row["status"]
                ),
                "created_at": row.get("created_at", run["created_at"]),
                "mode": run["mode"],
                "purpose": run.get("purpose", "business"),
                "can_decide": ready and not blocked and row["status"] == "pending",
                "blocked_reason": blocked,
            }
            for key in (
                "decided_at",
                "decision_note",
                "reviewer",
                "tool",
                "args",
                "result",
                "origin",
            ):
                if key in row:
                    item[key] = deepcopy(row[key])
            items.append(item)
    return items
