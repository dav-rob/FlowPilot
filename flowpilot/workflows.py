"""Declarative workflow contracts; shared engine and ordinary tools implement execution."""

COMMON_OUTCOMES = {
    "no_action_required",
    "no_business_action",
    "request_clarification",
    "request_supporting_evidence",
    "manual_review",
}
WORKFLOW_OUTCOMES = {
    "supplier_fraud": {
        "approve_and_process",
        "approve_bank_change",
        "hold_payment_and_open_fraud_case",
        "reject_change_and_open_fraud_case",
        "callback_verification_required",
        "reject_duplicate_invoice",
        "query_supplier_discrepancy",
        "no_action_already_applied",
    },
    "regulatory_compliance": {
        "no_action_required",
        "open_audit_item_gap_found",
        "monitor_approved_exception",
        "request_owner_attestation",
    },
    "gdpr_data": {
        "fulfil_erasure",
        "refuse_erasure_legal_hold",
        "partial_erasure_with_retention_exemption",
        "fulfil_access_request",
        "request_identity_verification",
        "reject_third_party_request",
        "apply_correction",
        "request_supporting_evidence",
        "refer_to_security_review",
        "no_record_found_notify_requester",
    },
    "it_asset": {
        "register_asset_and_assign_owner",
        "isolate_and_open_incident",
        "decommission_stale_asset",
        "reconcile_inventory_record",
        "complete_decommission_with_ticket",
        "close_as_authorised_activity",
        "recover_device_and_open_ticket",
    },
    "contract_risk": {
        "route_for_standard_approval",
        "escalate_to_senior_approval",
        "block_pending_privacy_assessment",
        "request_clause_renegotiation",
        "request_missing_documents",
    },
}


def outcome_codes(categories):
    allowed = set(COMMON_OUTCOMES)
    for domain in categories:
        allowed.update(WORKFLOW_OUTCOMES.get(domain, ()))
    return sorted(allowed)
