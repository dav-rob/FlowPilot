"""Explicit deterministic demonstration policy; never represented as a model call.

This policy branches on returned records and is useful offline. It does not use
presenter paths, expected outcomes, scenario family IDs or ground truth.
"""

import json
import re


def records(value):
    if isinstance(value, dict):
        if "id" in value:
            yield value
        for v in value.values():
            yield from records(v)
    elif isinstance(value, list):
        for v in value:
            yield from records(v)


def simulation_step(document, categories, observations, iteration):
    calls = [(o["tool"], o["arguments"]) for o in observations]
    results = [
        o["result"].get("data", {}) for o in observations if o["result"].get("ok")
    ]
    rows = list(records(results))
    raw = json.dumps(results).lower()
    ids = lambda prefix: list(
        dict.fromkeys(
            r["id"] for r in rows if str(r.get("id", "")).startswith(prefix + "-")
        )
    )

    def done(tool, args):
        return (tool, args) in calls

    def action(tool, args, why):
        return {"tool": tool, "arguments": json.dumps(args), "rationale": why}

    def new(tool, args, why):
        return None if done(tool, args) else action(tool, args, why)

    # A single bounded retry for transient service errors; alternate tools otherwise.
    for o in observations[-4:]:
        e = o["result"].get("error", {})
        if (
            e.get("code") == "SERVICE_UNAVAILABLE"
            and e.get("retryable")
            and calls.count((o["tool"], o["arguments"])) < 2
        ):
            return {
                "kind": "calls",
                "rationale": "The service reported a transient failure; retry once.",
                "actions": [
                    action(
                        o["tool"],
                        o["arguments"],
                        "Retry the explicitly retryable service failure.",
                    )
                ],
            }
    for o in observations:
        if (
            o["tool"] == "verify_email_origin"
            and not o["result"].get("ok")
            and calls.count((o["tool"], o["arguments"])) >= 2
        ):
            alt = {"message_id": o["arguments"]["message_id"]}
            if not done("get_email_headers", alt):
                return {
                    "kind": "calls",
                    "rationale": "Gateway verification remains unavailable; inspect the independent mail archive.",
                    "actions": [
                        action(
                            "get_email_headers",
                            alt,
                            "Use archived authentication headers as alternate evidence.",
                        )
                    ],
                }
    actions = []
    for domain in categories:
        pending = []

        def add(t, a, w):
            n = new(t, a, w)
            if n:
                pending.append(n)

        if domain == "supplier_fraud":
            inv = re.search(r"\b(?:SI|INV)[- ]\d{4,}\b", document, re.I)
            if not ids("INV") and inv:
                add(
                    "search_invoices",
                    {"invoice_number": inv.group().replace(" ", "-")},
                    "Resolve the invoice reference before checking the supplier.",
                )
            elif ids("INV"):
                i = next(r for r in rows if r.get("id") == ids("INV")[0])
                sup = i.get("supplier_id")
                if sup:
                    add(
                        "get_supplier_record",
                        {"supplier_id": sup},
                        "Compare the invoice against the registered supplier and bank account.",
                    )
                m = i.get("message_id") or i.get("source_message_id")
                if not m:
                    mm = re.search(
                        r'"message_reference"\s*:\s*"([^"\n]+)"|Message-ID:\s*<?([^>\n]+)',
                        document,
                        re.I,
                    )
                    m = (mm.group(1) or mm.group(2)) if mm else None
                if m:
                    add(
                        "verify_email_origin",
                        {"message_id": m},
                        "Validate the source of the payment instruction.",
                    )
                if sup and (
                    ids("SUP")
                    and any(
                        x in document.lower() for x in ("change", "account", "bank")
                    )
                ):
                    add(
                        "get_supplier_change_history",
                        {"supplier_id": sup},
                        "A bank instruction warrants checking its authorisation history.",
                    )
                    if "changes" in raw:
                        add(
                            "get_callback_log",
                            {"supplier_id": sup},
                            "Check independent callback verification of the change.",
                        )
                if i.get("purchase_order_id"):
                    add(
                        "get_purchase_order",
                        {"po_id": i["purchase_order_id"]},
                        "Check that the invoice is supported by a purchase order.",
                    )
            else:
                vat = re.search(r"\bGB\d{9}\b", document)
                if vat:
                    add(
                        "find_supplier",
                        {"vat_number": vat.group()},
                        "Resolve the supplier from its VAT reference.",
                    )
                for s in ids("SUP"):
                    add(
                        "get_supplier_change_history",
                        {"supplier_id": s},
                        "Inspect the requested change history.",
                    )
        elif domain == "regulatory_compliance":
            ref = re.search(r"\b(?:FFSB|POL)[-A-Z0-9]*\d\b", document)
            if not ids("POL"):
                add(
                    "search_records",
                    {
                        "query": (
                            ref.group()
                            if ref
                            else " ".join(re.findall(r"[A-Za-z]{5,}", document)[:6])
                        ),
                        "record_types": ["policy"],
                    },
                    "Locate the policy and its applicability criteria.",
                )
            else:
                for p in ids("POL")[:1]:
                    add(
                        "get_policy",
                        {"policy_id": p},
                        "Read the actual obligation before choosing audit tests.",
                    )
                    add(
                        "discover_affected_systems",
                        {"policy_id": p},
                        "Identify in-scope systems from policy criteria.",
                    )
                scoped = [s for r in results for s in r.get("in_scope", [])]
                for s in scoped[:4]:
                    if any(
                        x in document.lower()
                        for x in ("mfa", "privileged", "access", "sign-in")
                    ):
                        add(
                            "get_access_grants",
                            {"system_id": s["id"], "privileged_only": True},
                            "Test privileged accounts against the access requirement.",
                        )
                    else:
                        add(
                            "inspect_security_controls",
                            {"system_id": s["id"]},
                            "Inspect controls relevant to the new obligation.",
                        )
                    if any(
                        o["tool"] in ("get_access_grants", "inspect_security_controls")
                        and o["arguments"].get("system_id") == s["id"]
                        for o in observations
                    ):
                        add(
                            "get_control_exceptions",
                            {"system_id": s["id"]},
                            "Check whether a discovered gap has an approved exception.",
                        )
        elif domain == "gdpr_data":
            ref = re.search(r"\bC\d{7,}\b", document)
            email = re.search(r"[\w.+-]+@[\w.-]+\.example", document)
            if not ids("CUS"):
                args = (
                    {"customer_reference": ref.group()}
                    if ref
                    else {"email": email.group()} if email else None
                )
                if args:
                    add(
                        "find_customer",
                        args,
                        "Resolve the requester in CRM using the supplied identifier.",
                    )
            else:
                c = ids("CUS")[0]
                add(
                    "verify_identity_status",
                    {"customer_id": c},
                    "Verify identity before preparing any disclosure or change.",
                )
                add(
                    "get_audit_trail",
                    {"record_id": c},
                    "Check recent account changes and unusual activity.",
                )
                ver = [v for r in results for v in r.get("verifications", [])]
                verified = any(
                    v.get("outcome") in ("passed", "verified", "pass")
                    and not v.get("expired")
                    for v in ver
                )
                if verified:
                    add(
                        "find_customer_data",
                        {"customer_id": c},
                        "Discover where the customer has personal data.",
                    )
                    add(
                        "check_legal_holds",
                        {"customer_id": c},
                        "Determine whether legal restrictions prevent deletion.",
                    )
                    add(
                        "get_retention_records",
                        {"customer_id": c},
                        "Separate eligible records from mandatory retention.",
                    )
        elif domain == "it_asset":
            host = re.search(r"Hostname\s*[:|]\s*([^\s|]+)", document, re.I)
            ip = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", document)
            if not ids("CI") and not ids("CLD"):
                args = (
                    {"hostname": host.group(1)}
                    if host
                    else {"ip_address": ip.group()} if ip else None
                )
                if args:
                    add(
                        "search_assets",
                        args,
                        "Cross-reference the discovered host against the asset inventory.",
                    )
                # Ambiguous results are themselves evidence and can be narrowed via candidate IDs.
                for o in observations:
                    for c in o["result"].get("error", {}).get("candidates", [])[:3]:
                        if c["id"].startswith("CI-"):
                            add(
                                "get_cmdb_item",
                                {"asset_id": c["id"]},
                                "Inspect each conflicting inventory candidate.",
                            )
            else:
                for a in (ids("CI") + ids("CLD"))[:2]:
                    add(
                        "get_security_alerts",
                        {"asset_id": a},
                        "Check whether the mismatch has associated security alerts.",
                    )
                    add(
                        "lookup_asset_owner",
                        {"asset_id": a},
                        "Resolve accountable ownership from the directory.",
                    )
                    add(
                        "get_deployment_history",
                        {"asset_id": a},
                        "Check whether a migration explains the inventory mismatch.",
                    )
                for c in ids("CRQ")[:2]:
                    add(
                        "get_change_record",
                        {"change_id": c},
                        "Verify authorisation of the deployment change.",
                    )
        elif domain == "contract_risk":
            ref = re.search(r"\bAGR-\d+\b", document)
            if not ids("CTR") and ref:
                add(
                    "find_contracts",
                    {"contract_number": ref.group()},
                    "Locate the contract before assessing changed terms.",
                )
            elif ids("CTR"):
                c = ids("CTR")[0]
                add(
                    "get_contract",
                    {"contract_id": c},
                    "Inspect execution status and the current contract version.",
                )
                add(
                    "compare_contract_versions",
                    {"contract_id": c},
                    "Compare the actual clauses to select departmental reviews.",
                )
                changes = [d for r in results for d in r.get("changed_clauses", [])]
                clauses = json.dumps(changes).lower()
                if "signed" in document.lower() or "executed" in raw:
                    add(
                        "get_approval_workflow",
                        {"contract_id": c},
                        "Check whether approvals were completed before signature.",
                    )
                if any(
                    x in clauses
                    for x in ("price", "charge", "annual", "value", "liability")
                ):
                    add(
                        "get_financial_controls",
                        {"contract_id": c},
                        "Check delegated authority for changed financial exposure.",
                    )
                if any(
                    x in clauses
                    for x in ("hosting", "data", "subprocessor", "location", "security")
                ):
                    add(
                        "get_privacy_assessment",
                        {"contract_id": c},
                        "Changed data processing terms require a privacy assessment.",
                    )
                if any(x in clauses for x in ("hosting", "liability", "subprocessor")):
                    for s in ids("SUP")[:1]:
                        add(
                            "get_supplier_risk",
                            {"supplier_id": s},
                            "Check supplier risk where the amendment changes exposure.",
                        )
        # Stage batches so observed data can change later selections.
        actions.extend(pending[:3])
    if actions and iteration < 10:
        return {
            "kind": "calls",
            "rationale": "Deterministic simulation: choose the next relevant checks from returned evidence.",
            "actions": actions[:4],
        }
    evidence = []
    seen = set()
    for r in rows:
        rid = r["id"]
        if rid in seen:
            continue
        seen.add(rid)
        note = next(
            (
                str(r[k])
                for k in (
                    "summary",
                    "title",
                    "name",
                    "full_name",
                    "hostname",
                    "status",
                    "outcome",
                )
                if r.get(k)
            ),
            "Record returned by a business tool.",
        )
        evidence.append({"record_id": rid, "note": note[:300]})
    # Include gateway IDs returned outside ordinary record objects.
    for r in results:
        if r.get("message_record_id") and r["message_record_id"] not in seen:
            evidence.append(
                {
                    "record_id": r["message_record_id"],
                    "note": str(r.get("analysis", "Mail gateway evidence."))[:300],
                }
            )
    risk = "medium"
    code = "request_supporting_evidence"
    summary = "Review the collected evidence before taking action."
    recommendations = []
    unresolved = []
    departments = []
    domain_outcomes = {}
    if "supplier_fraud" in categories:
        suspicious = any(
            x in raw
            for x in (
                "lookalike",
                "impersonation",
                '"dmarc": "fail"',
                '"spf": "fail"',
                "spf=fail",
                "dmarc=fail",
                '"authorised": false',
                '"authorized": false',
            )
        )
        if suspicious:
            risk = "critical"
            code = "hold_payment_and_open_fraud_case"
            summary = "Payment instruction requires fraud review; gateway or authorisation evidence is suspicious."
            recommendations.append(
                "Withhold payment pending an independently verified callback and fraud review."
            )
            invs = ids("INV")
            if invs and not any(o["tool"] == "request_approval" for o in observations):
                return {
                    "kind": "calls",
                    "rationale": "Suspicious evidence warrants a proposed hold; a human must authorise it.",
                    "actions": [
                        action(
                            "request_approval",
                            {
                                "action": "place_payment_hold",
                                "arguments": {
                                    "invoice_id": invs[0],
                                    "reason": "Suspicious source or unauthorised payment instruction.",
                                },
                                "justification": "Gateway and supplier evidence warrant a simulated hold pending fraud review.",
                            },
                            "Request human approval; do not execute a financial action.",
                        )
                    ],
                }
        else:
            code = "callback_verification_required"
            summary = "Supplier and invoice checks collected; independently verify payment instructions before release."
        departments.append("Finance")
        domain_outcomes["supplier_fraud"] = code
    if "regulatory_compliance" in categories:
        gap = any(
            r.get("privileged")
            and r.get("account_type") == "human"
            and not r.get("mfa_enabled")
            for r in rows
        ) or any(
            r.get("status") in ("failed", "missing", "not_implemented", "non_compliant")
            for r in rows
        )
        code = "open_audit_item_gap_found" if gap else "request_owner_attestation"
        risk = "high" if gap else "medium"
        summary = (
            "The policy investigation found a control gap requiring owner review."
            if gap
            else "Policy scope and controls investigated; request owner attestation for remaining uncertainty."
        )
        recommendations.append(
            "Record the audit evidence and assign remediation to the system owner."
        )
        departments.append("Compliance")
        domain_outcomes["regulatory_compliance"] = code
    if "gdpr_data" in categories:
        failed = any(r.get("outcome") in ("failed", "fail", "rejected") for r in rows)
        holds = any(
            r.get("status") == "active" and r.get("id", "").startswith("LGH-")
            for r in rows
        )
        code = (
            "refer_to_security_review"
            if failed
            else "refuse_erasure_legal_hold" if holds else "request_supporting_evidence"
        )
        risk = "high" if failed or holds else "medium"
        summary = (
            "Identity evidence prevents safe fulfilment; refer the request for security review."
            if failed
            else (
                "A legal hold limits the requested action."
                if holds
                else "Data request investigated; prepare a scoped proposal after identity and retention review."
            )
        )
        recommendations.append(
            "Keep disclosure, correction and deletion on hold until identity and legal restrictions are resolved."
        )
        departments.append("Privacy")
        domain_outcomes["gdpr_data"] = code
    if "it_asset" in categories:
        suspicious = any(
            x in raw
            for x in (
                "rogue",
                "masquerad",
                "malicious",
                "command and control",
                "unauthorised",
            )
        ) or any(
            r.get("id", "").startswith("ALT-")
            and r.get("severity") in ("high", "critical")
            and r.get("status") == "open"
            for r in rows
        )
        code = (
            "isolate_and_open_incident" if suspicious else "reconcile_inventory_record"
        )
        risk = "critical" if suspicious else "low"
        summary = (
            "Security evidence suggests an unauthorised asset; incident review and controlled containment are required."
            if suspicious
            else "Inventory and ownership evidence suggests reconciliation or owner follow-up."
        )
        recommendations.append(
            "Ask the security owner to review containment."
            if suspicious
            else "Reconcile the inventory against approved deployment records."
        )
        departments.append("IT Operations")
        domain_outcomes["it_asset"] = code
    if "contract_risk" in categories:
        code = (
            "escalate_to_senior_approval"
            if "signed" in document.lower() or "executed" in raw
            else "route_for_standard_approval"
        )
        risk = "high" if code == "escalate_to_senior_approval" else "medium"
        summary = "Contract evidence collected; approval gaps or changed obligations require departmental review."
        changes = json.dumps(
            [d for r in results for d in r.get("changed_clauses", [])]
        ).lower()
        departments.extend(
            ["Legal"]
            if any(x in changes for x in ("liability", "termination", "jurisdiction"))
            else []
        )
        departments.extend(
            ["Finance"]
            if any(x in changes for x in ("price", "annual", "charge", "value"))
            else []
        )
        departments.extend(
            ["Privacy", "Security"]
            if any(
                x in changes for x in ("hosting", "data", "security", "subprocessor")
            )
            else []
        )
        domain_outcomes["contract_risk"] = code
        recommendations.append(
            "Route only the changed obligations to the responsible reviewers; signature remains approval-gated."
        )
    if not evidence:
        code = "request_clarification"
        risk = "low"
        summary = "No reliable business records were resolved from the supplied input."
        unresolved.append(
            "Provide a supplier, policy, customer, asset or contract identifier."
        )
    if len(categories) > 1:
        unresolved.append(
            "This cross-domain simulation aggregates checks; a human must reconcile the combined outcome."
        )
    return {
        "kind": "finish",
        "rationale": "Deterministic simulation has reached its evidence boundary.",
        "actions": [],
        "outcome": {
            "summary": summary,
            "conclusion": summary,
            "risk": risk,
            "outcome_code": code,
            "evidence": evidence[:18],
            "unresolved": unresolved,
            "recommendations": recommendations,
            "requires_approval": False,
            "actions": [],
            "departments": list(dict.fromkeys(departments)),
            "by_workflow": domain_outcomes,
        },
    }
