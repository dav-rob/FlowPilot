"""Shared constants: tables, categories, outcome metadata, tool taxonomy."""
from __future__ import annotations

PARTITIONS = ["train", "validation", "test"]
PARTITION_SHARE = {"train": 0.6, "validation": 0.2, "test": 0.2}

DOMAINS = ["supplier_fraud", "regulatory_compliance", "gdpr_data", "it_asset", "contract_risk"]
CROSS = "cross_domain"
DISTRACTOR = "distractor"
GROUPS = DOMAINS + [CROSS, DISTRACTOR]
OUT_OF_SCOPE = "out_of_scope"
CATEGORIES = DOMAINS + [OUT_OF_SCOPE]
DIFFICULTIES = ["straightforward", "moderate", "difficult"]
DIFFICULTY_SHARE = [0.5, 0.3, 0.2]

# table -> (id prefix, searchable fields)
TABLES: dict[str, tuple[str, list[str]]] = {
    "suppliers": ("SUP", ["name", "trading_names", "vat_number", "company_number", "email_domain", "status"]),
    "supplier_bank_accounts": ("BAC", ["account_name", "account_number", "iban", "sort_code"]),
    "supplier_contacts": ("SCT", ["name", "email", "phone"]),
    "supplier_changes": ("SCR", ["summary", "requested_by_email"]),
    "callback_log": ("CBK", ["called_number", "notes"]),
    "invoices": ("INV", ["invoice_number", "po_reference", "description"]),
    "purchase_orders": ("PO", ["po_number", "description"]),
    "goods_receipts": ("GRN", ["description"]),
    "payments": ("PAY", ["payment_reference"]),
    "email_messages": ("MSG", ["sender", "reply_to", "subject", "rfc_message_id"]),
    "fraud_cases": ("FRD", ["summary", "beneficiary_account_number"]),
    "policies": ("POL", ["title", "reference", "summary"]),
    "systems": ("SYS", ["name", "aliases", "description"]),
    "control_catalogue": ("CCT", ["title", "reference"]),
    "controls": ("CTL", ["control_ref"]),
    "databases": ("DBS", ["name", "engine"]),
    "access_grants": ("ACG", ["principal", "role"]),
    "audit_findings": ("AUD", ["title", "summary"]),
    "control_exceptions": ("EXC", ["title", "justification"]),
    "audit_log": ("LOG", ["summary"]),
    "customers": ("CUS", ["full_name", "email", "postcode", "customer_reference", "previous_names"]),
    "customer_products": ("PRD", ["product_name", "account_reference"]),
    "identity_verifications": ("IDV", ["method"]),
    "datasets": ("DST", ["name", "description"]),
    "data_locations": ("DLC", ["record_locator"]),
    "retention_rules": ("RET", ["rule_name"]),
    "legal_holds": ("LGH", ["matter_reference", "reason"]),
    "data_requests": ("DSR", ["summary", "request_reference"]),
    "authority_letters": ("ATH", ["signatory", "summary"]),
    "employees": ("EMP", ["name", "email", "username"]),
    "cmdb_items": ("CI", ["hostname", "serial_number", "ip_address", "mac_address", "asset_tag", "description"]),
    "cloud_resources": ("CLD", ["resource_name", "public_ip", "private_ip", "resource_type"]),
    "deployments": ("DEP", ["service_name", "summary"]),
    "changes": ("CRQ", ["title", "summary"]),
    "tickets": ("TKT", ["title", "summary"]),
    "security_alerts": ("ALT", ["title", "summary", "process_name"]),
    "contracts": ("CTR", ["title", "contract_number", "counterparty_name"]),
    "contract_versions": ("CVR", ["change_summary"]),
    "supplier_risk": ("RSK", ["summary"]),
    "delegated_authority": ("DAU", ["role_title"]),
    "privacy_assessments": ("PIA", ["title", "summary"]),
    "approval_workflows": ("WFL", ["summary"]),
    "service_status": ("SVC", ["tool"]),
    "evidence_documents": ("EVD", ["title", "text"]),
}
_SING_EXC = {"service_status": "service_status", "supplier_risk": "supplier_risk", "callback_log": "callback_log",
             "audit_log": "audit_log", "delegated_authority": "delegated_authority"}
SINGULAR = {t: _SING_EXC.get(t, t[:-3] + "y" if t.endswith("ies") else t[:-1] if t.endswith("s") else t) for t in TABLES}
TYPE_TO_TABLE = {v: k for k, v in SINGULAR.items()}
PREFIX_TO_TABLE = {v[0]: k for k, v in TABLES.items()}

# --- outcomes: outcome -> metadata used to derive risk/review/sensitivity from scenario facts
# risk: base risk level; human_review: whether a human must decide; sensitive: sensitive tool the
# outcome would legitimately use (with approval).
OUTCOMES: dict[str, dict] = {
    # supplier fraud
    "approve_and_process": {"risk": "low", "human_review": False, "sensitive": ["release_payment"]},
    "approve_bank_change": {"risk": "medium", "human_review": False, "sensitive": ["update_supplier_bank_details"]},
    "hold_payment_and_open_fraud_case": {"risk": "critical", "human_review": True, "sensitive": ["place_payment_hold"]},
    "reject_change_and_open_fraud_case": {"risk": "high", "human_review": True, "sensitive": []},
    "callback_verification_required": {"risk": "medium", "human_review": False, "sensitive": []},
    "reject_duplicate_invoice": {"risk": "medium", "human_review": False, "sensitive": []},
    "query_supplier_discrepancy": {"risk": "medium", "human_review": False, "sensitive": []},
    "no_action_already_applied": {"risk": "low", "human_review": False, "sensitive": []},
    # compliance
    "no_action_required": {"risk": "low", "human_review": False, "sensitive": []},
    "open_audit_item_gap_found": {"risk": "high", "human_review": True, "sensitive": []},
    "monitor_approved_exception": {"risk": "medium", "human_review": False, "sensitive": []},
    "request_owner_attestation": {"risk": "medium", "human_review": False, "sensitive": []},
    # gdpr
    "fulfil_erasure": {"risk": "medium", "human_review": False, "sensitive": ["execute_erasure"]},
    "refuse_erasure_legal_hold": {"risk": "high", "human_review": True, "sensitive": []},
    "partial_erasure_with_retention_exemption": {"risk": "medium", "human_review": True, "sensitive": ["execute_erasure"]},
    "fulfil_access_request": {"risk": "medium", "human_review": False, "sensitive": ["export_customer_data"]},
    "request_identity_verification": {"risk": "medium", "human_review": False, "sensitive": []},
    "reject_third_party_request": {"risk": "high", "human_review": True, "sensitive": []},
    "apply_correction": {"risk": "low", "human_review": False, "sensitive": ["update_customer_record"]},
    "request_supporting_evidence": {"risk": "low", "human_review": False, "sensitive": []},
    "refer_to_security_review": {"risk": "high", "human_review": True, "sensitive": []},
    "no_record_found_notify_requester": {"risk": "low", "human_review": False, "sensitive": []},
    # it asset
    "register_asset_and_assign_owner": {"risk": "low", "human_review": False, "sensitive": []},
    "isolate_and_open_incident": {"risk": "critical", "human_review": True, "sensitive": ["isolate_asset"]},
    "decommission_stale_asset": {"risk": "medium", "human_review": False, "sensitive": ["decommission_asset"]},
    "reconcile_inventory_record": {"risk": "low", "human_review": False, "sensitive": []},
    "complete_decommission_with_ticket": {"risk": "medium", "human_review": False, "sensitive": ["decommission_asset"]},
    "close_as_authorised_activity": {"risk": "low", "human_review": False, "sensitive": []},
    "recover_device_and_open_ticket": {"risk": "high", "human_review": True, "sensitive": []},
    # contract
    "route_for_standard_approval": {"risk": "low", "human_review": False, "sensitive": []},
    "escalate_to_senior_approval": {"risk": "high", "human_review": True, "sensitive": []},
    "block_pending_privacy_assessment": {"risk": "high", "human_review": True, "sensitive": []},
    "request_clause_renegotiation": {"risk": "medium", "human_review": True, "sensitive": []},
    "request_missing_documents": {"risk": "medium", "human_review": False, "sensitive": []},
    # distractors / generic
    "no_business_action": {"risk": "low", "human_review": False, "sensitive": []},
    "request_clarification": {"risk": "low", "human_review": False, "sensitive": []},
    "reject_unsupported_request": {"risk": "medium", "human_review": True, "sensitive": []},
}
RISK_LEVELS = ["low", "medium", "high", "critical"]

SENSITIVE_TOOLS = {
    "place_payment_hold": "finance", "release_payment": "finance", "update_supplier_bank_details": "finance",
    "release_contract_for_signature": "finance", "revoke_access_grant": "security", "isolate_asset": "security",
    "decommission_asset": "security", "execute_erasure": "deletion", "export_customer_data": "data_disclosure",
    "update_customer_record": "data_change",
}

# Tool -> workflow domain (used for relevance/inappropriateness derivation).
TOOL_DOMAIN = {
    "get_supplier_record": "supplier_fraud", "find_supplier": "supplier_fraud", "get_supplier_change_history": "supplier_fraud",
    "get_invoice": "supplier_fraud", "search_invoices": "supplier_fraud", "get_purchase_order": "supplier_fraud",
    "get_goods_receipts": "supplier_fraud", "verify_email_origin": "supplier_fraud", "get_email_headers": "supplier_fraud",
    "get_callback_log": "supplier_fraud", "get_payment_status": "supplier_fraud", "find_account_usage": "supplier_fraud",
    "get_fraud_cases": "supplier_fraud", "place_payment_hold": "supplier_fraud", "release_payment": "supplier_fraud",
    "update_supplier_bank_details": "supplier_fraud",
    "get_policy": "regulatory_compliance", "discover_affected_systems": "regulatory_compliance",
    "get_system": "regulatory_compliance", "inspect_security_controls": "regulatory_compliance",
    "get_control_definition": "regulatory_compliance", "run_database_query": "regulatory_compliance",
    "list_system_databases": "regulatory_compliance", "get_access_grants": "regulatory_compliance",
    "get_audit_findings": "regulatory_compliance", "get_control_exceptions": "regulatory_compliance",
    "revoke_access_grant": "regulatory_compliance",
    "find_customer": "gdpr_data", "get_customer_record": "gdpr_data", "verify_identity_status": "gdpr_data",
    "find_customer_data": "gdpr_data", "get_retention_records": "gdpr_data", "check_legal_holds": "gdpr_data",
    "get_data_request_history": "gdpr_data", "get_third_party_authority": "gdpr_data",
    "export_customer_data": "gdpr_data", "execute_erasure": "gdpr_data", "update_customer_record": "gdpr_data",
    "lookup_asset_owner": "it_asset", "query_cloud_inventory": "it_asset", "get_cmdb_item": "it_asset",
    "search_assets": "it_asset", "get_deployment_history": "it_asset", "get_change_record": "it_asset",
    "get_security_alerts": "it_asset", "get_employee": "it_asset", "get_ticket": "it_asset",
    "isolate_asset": "it_asset", "decommission_asset": "it_asset",
    "get_contract": "contract_risk", "compare_contract_versions": "contract_risk", "get_supplier_risk": "contract_risk",
    "get_financial_controls": "contract_risk", "get_privacy_assessment": "contract_risk",
    "get_approval_workflow": "contract_risk", "find_contracts": "contract_risk",
    "release_contract_for_signature": "contract_risk",
}
GENERIC_TOOLS = ["search_records", "get_linked_records", "get_audit_trail", "create_review_case", "create_ticket",
                 "request_approval", "list_tools"]
# outage -> alternate path (same evidence reachable another way)
ALTERNATES = {
    "verify_email_origin": "get_email_headers",
    "get_supplier_change_history": "search_records",
    "inspect_security_controls": "search_records",
    "check_legal_holds": "search_records",
    "lookup_asset_owner": "get_cmdb_item",
    "get_supplier_risk": "search_records",
}
