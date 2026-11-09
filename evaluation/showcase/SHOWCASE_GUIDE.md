# Showcase guide (evaluator/presenter only - not agent input)

Five curated cases, one per workflow, drawn from the **train** partition so the held-out test set is not spent on demos.
Selection is automatic and deterministic: highest score for dependent investigation depth, alternative paths, outages, conflicting evidence and risk.
The `example_path` below is a presenter/evaluator walkthrough fixture illustrating one valid investigation trajectory; an AI agent receives only the public case input and selects tools dynamically.
Run a walkthrough: `python -m flowpilot_data showcase` (or `--case <case_id>` / `--workflow <workflow>`).

## supplier_fraud: `IN-B148DF6144`
* Input: `data/partitions/train/inbox/DOC-3F9861DDF0.event.json`
* Scenario: Urgent payment instruction to a recent supplier (no_po_urgent_fraud).
* Expected outcome: `hold_payment_and_open_fraud_case` (risk critical, human review True)
* Why it demos well: 6 valid investigation paths, simulated service outage with recovery, conflicting evidence, critical risk with a sensitive action to withhold or approve, category not clear from the input alone
* Evidence a good investigation finds: `MSG-0C0E250E` (executive_impersonation), `SUP-47D4A998` (onboarding_incomplete_new_supplier)
* Example valid path (presenter fixture; others exist): `search_invoices` -> `get_supplier_record` -> `verify_email_origin`

## regulatory_compliance: `IN-4988DE6162`
* Input: `data/partitions/train/inbox/DOC-547ED9C90C.md`
* Scenario: MFA notice (privileged_gap).
* Expected outcome: `open_audit_item_gap_found` (risk high, human review True)
* Why it demos well: 4 valid investigation paths, conflicting evidence, high risk with a sensitive action to withhold or approve, category not clear from the input alone
* Evidence a good investigation finds: `ACG-5257D030` (human_privileged_without_mfa)
* Example valid path (presenter fixture; others exist): `search_records` -> `discover_affected_systems` -> `get_access_grants`

## gdpr_data: `IN-D687B92A2F`
* Input: `data/partitions/train/inbox/DOC-201B6F3EC9.events.jsonl`
* Scenario: Customer asks to correct personal data (account_takeover_suspected).
* Expected outcome: `refer_to_security_review` (risk high, human review True)
* Why it demos well: 6 valid investigation paths, conflicting evidence, high risk with a sensitive action to withhold or approve
* Evidence a good investigation finds: `LOG-4A0469CE` (recent_contact_changes_new_device), `LOG-BB08C7BC` (recent_contact_changes_new_device), `IDV-F54272E7` (identity_check_failed)
* Example valid path (presenter fixture; others exist): `find_customer` -> `get_audit_trail` -> `verify_identity_status`

## it_asset: `IN-F8352D982B`
* Input: `data/partitions/train/inbox/DOC-52A952A3F5.txt`
* Scenario: CMDB / discovery discrepancy (rogue_host_masquerading).
* Expected outcome: `isolate_and_open_incident` (risk critical, human review True)
* Why it demos well: conflicting evidence, critical risk with a sensitive action to withhold or approve, category not clear from the input alone
* Evidence a good investigation finds: `ALT-3733ABEF` (mac_mismatch_masquerade), `CI-B33F4001` (registered_mac_differs), `TKT-1B2F7E43` (stale_ownership_claim)
* Example valid path (presenter fixture; others exist): `search_assets` -> `get_security_alerts` -> `get_cmdb_item`

## contract_risk: `IN-8649D7CEB6`
* Input: `data/partitions/train/inbox/DOC-151D8EB69E.eml`
* Scenario: Retrospective approval check (executed_without_approval).
* Expected outcome: `escalate_to_senior_approval` (risk high, human review True)
* Why it demos well: 4 valid investigation paths, conflicting evidence, high risk with a sensitive action to withhold or approve, category not clear from the input alone
* Evidence a good investigation finds: `WFL-DE949059` (approval_not_completed_before_signature), `CTR-8649A3D3` (contract_already_executed)
* Example valid path (presenter fixture; others exist): `find_contracts` -> `get_approval_workflow` -> `get_contract`
