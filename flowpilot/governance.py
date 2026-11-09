"""Deterministic synthetic-data constraints independent of model output and human consent."""

from flowpilot_data.util import REFERENCE_NOW


def data_action_guard(session, action, args):
    if action not in (
        "execute_erasure",
        "export_customer_data",
        "update_customer_record",
    ):
        return None
    cid = args.get("customer_id")
    today = REFERENCE_NOW.strftime("%Y-%m-%d")
    checks = sorted(
        (
            r
            for r in session.env.rows("identity_verifications")
            if r["customer_id"] == cid
        ),
        key=lambda r: (r["checked_on"], r["id"]),
        reverse=True,
    )
    if (
        not checks
        or checks[0]["outcome"] != "passed"
        or checks[0]["expires_on"] < today
    ):
        return {
            "code": "IDENTITY_NOT_VERIFIED",
            "message": "The latest synthetic identity check is missing, failed or expired. Human approval cannot replace identity verification.",
        }
    if action == "update_customer_record":
        changes = args.get("changes", {})
        if not changes or set(changes) - {
            "full_name",
            "address",
            "email",
            "postcode",
            "phone",
        }:
            return {
                "code": "INVALID_ARGUMENT",
                "message": "Only supported customer contact fields may be corrected.",
            }
    if action == "execute_erasure":
        requested = set(args.get("dataset_ids", []))
        locations = [
            r
            for r in session.env.rows("data_locations")
            if r["customer_id"] == cid and r["dataset_id"] in requested
        ]
        if not requested or {r["dataset_id"] for r in locations} != requested:
            return {
                "code": "INVALID_ARGUMENT",
                "message": "The proposed datasets must hold records for this customer.",
            }
        holds = [
            h
            for h in session.env.rows("legal_holds")
            if h["customer_id"] == cid
            and h["status"] == "active"
            and (not h.get("dataset_ids") or requested.intersection(h["dataset_ids"]))
        ]
        if holds:
            return {
                "code": "LEGAL_HOLD",
                "message": "An active synthetic legal hold covers the proposed records. Erasure is blocked even with human approval.",
                "evidence_ids": [h["id"] for h in holds],
            }
        retained = [
            r
            for r in locations
            if not r.get("eligible_for_erasure_on")
            or r["eligible_for_erasure_on"] > today
        ]
        if retained:
            return {
                "code": "RETENTION_REQUIRED",
                "message": "The synthetic retention schedule does not yet permit erasure of every proposed dataset.",
                "dataset_ids": sorted({r["dataset_id"] for r in retained}),
            }
    return None
