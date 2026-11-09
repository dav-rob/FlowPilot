"""Contract risk assessment families (contract repository / supplier risk / financial controls / privacy / approvals)."""
from __future__ import annotations

from ..docs import Attachment
from ..util import ago, day, future_day
from ..world import mk_bank, mk_contact, mk_contract, mk_supplier
from .base import Ctx, family
from .common import add_fluff, sender_internal, staff
from .. import vocab

CAT = "contract_risk"
BASE_CLAUSES = dict(liability_cap_gbp=5_000_000, data_processing_clause=True, auto_renewal=False, termination_notice_days=90, audit_rights=True,
                    subcontracting_permitted="with_consent", incident_notification_hours=24, payment_terms_days=30)


def _scaffold(ctx: Ctx, *, personal_data=None, value=None, limit_ok=True, n_versions=1, status="draft"):
    w, r = ctx.w, ctx.r
    proc, owner = staff(ctx, "Procurement")[0], staff(ctx, "Legal")[0]
    sup = ctx.adopt(mk_supplier(w, r, owner_employee_id=owner["id"]))
    ctx.adopt(mk_bank(w, r, sup)); ctx.adopt(mk_contact(w, r, sup))
    ctx.protect(sup["name"])
    pd = r.chance(0.5) if personal_data is None else personal_data
    annual = value or r.choice([60_000, 120_000, 240_000, 480_000, 900_000])
    con = ctx.adopt(mk_contract(w, r, sup, owner_employee_id=owner["id"], annual_value_gbp=annual, term_months=r.choice([12, 24, 36]), processes_personal_data=pd, status=status,
                                criticality=r.choice(["standard", "critical"])))
    total = annual * con["term_months"] / 12
    limit = total * 1.5 if limit_ok else total * 0.4
    dau = ctx.add("delegated_authority", employee_id=owner["id"], role_title="Head of Function", limit_gbp=round(limit, -3), granted_on=day(r.randrange(100, 900)), scope="supplier contracts")
    vers = []
    for n in range(1, n_versions + 1):
        cl = dict(BASE_CLAUSES)
        v = ctx.add("contract_versions", contract_id=con["id"], version_no=n, effective_date=day(r.randrange(2, 60) + (n_versions - n) * 90), clauses=cl, change_summary="Initial draft" if n == 1 else "Amendment", status="current" if n == n_versions else "superseded", author_id=proc["id"])
        vers.append(v)
    con["current_version_id"] = vers[-1]["id"]
    risk = ctx.add("supplier_risk", supplier_id=sup["id"], rating="medium", assessed_on=day(r.randrange(20, 200)), status="current", summary="Annual supplier risk assessment", factors=["concentration: low", "financial: stable"], sanctions_screening_status="clear", screening_date=day(r.randrange(10, 120)))
    wf = ctx.add("approval_workflows", contract_id=con["id"], summary="Standard supplier contract approval", status="not_started", steps=[{"role": "Procurement Lead", "status": "pending"}, {"role": "Legal", "status": "pending"}], started_on=None)
    ev = ctx.add("evidence_documents", title="Signed order form", text="Counter-signed signature page (synthetic)", record_id=con["id"], status="on_file")
    con["signatory_evidence_id"] = ev["id"]
    if ctx.conflicting:  # an older superseded draft with the same contract number
        old = ctx.add("contracts", **{**{k: v for k, v in con.items() if k != "id"}, "status": "superseded", "title": con["title"] + " (earlier draft)", "annual_value_gbp": round(annual * 0.5), "current_version_id": None})
        ctx.facts["earlier_draft"] = old["id"]; ctx.mark_conflict()
    return proc, owner, sup, con, vers, dau, risk, wf


def _pia(ctx, con, sup, status="approved", days=100, expires=300, summary="Privacy impact assessment for personal data processing (synthetic)"):
    return ctx.add("privacy_assessments", contract_id=con["id"], supplier_id=sup["id"], title="Supplier privacy impact assessment", summary=summary, status=status, completed_on=day(days), expires_on=future_day(expires) if expires >= 0 else day(-expires))


def _doc(ctx: Ctx, proc, con, sup, subject_alts, texts, vague, extra=()):
    sender_internal(ctx, proc)
    ctx.doc.to = f"contract.approvals@{vocab.COMPANY['domain']}"
    ctx.doc.subject = ctx.pick(subject_alts)
    ctx.say(*(vague if ctx.vague else texts))
    ctx.field("Contract number", con["contract_number"]); ctx.field("Supplier", sup["name"])
    for a, b in extra:
        ctx.field(a, b)
    ctx.maybe_field("Contract ID", con["id"], corrupt_ok=True)
    ctx.protect(con["contract_number"])
    add_fluff(ctx)


def _entry(con):
    return [("find_contracts", {"contract_number": con["contract_number"]})]


def _paths(ctx: Ctx, con, sup, calls):
    """calls: [(tool, args, finds)] each reachable after contract resolution."""
    e = _entry(con)
    ctx.path([con["id"]], *e)
    for tool, args, finds in calls:
        if finds:
            ctx.path(finds, *e, (tool, args))


@family("contract_new_supplier_approval", CAT, ["standard_route", "value_exceeds_authority", "missing_privacy_assessment"])
def contract_new_supplier_approval(ctx: Ctx):
    r, v = ctx.r, ctx.variant
    pd = True if v == "missing_privacy_assessment" else None
    proc, owner, sup, con, vers, dau, risk, wf = _scaffold(ctx, personal_data=pd, limit_ok=v != "value_exceeds_authority")
    ctx.add("contract_versions", contract_id=con["id"], version_no=0, effective_date=day(200), clauses=dict(BASE_CLAUSES), change_summary="Template baseline", status="superseded", author_id=proc["id"])
    ctx.records.append(ctx.w.tables["contract_versions"][-1]["id"])
    dec = []
    pia = None
    if v == "standard_route":
        if con["processes_personal_data"]:
            pia = _pia(ctx, con, sup); dec.append(ctx.ev(pia, "decisive", "privacy_assessment_current"))
        dec += [ctx.ev(dau, "decisive", "within_delegated_authority"), ctx.ev(risk, "supporting", "risk_acceptable")]
        outcome = "route_for_standard_approval"
    elif v == "value_exceeds_authority":
        if con["processes_personal_data"]:
            pia = _pia(ctx, con, sup); ctx.ev(pia, "supporting", "privacy_assessment_current")
        dec += [ctx.ev(dau, "decisive", "exceeds_delegated_authority"), ctx.ev(con, "decisive", "contract_value")]
        outcome = "escalate_to_senior_approval"
    else:
        if ctx.chance(0.5):
            pia = _pia(ctx, con, sup, status="expired", days=500, expires=-r.randrange(30, 200)); dec.append(ctx.ev(pia, "decisive", "privacy_assessment_expired"))
        else:
            dec.append(ctx.ev(con, "decisive", "personal_data_processing_no_assessment"))
        ctx.ev(dau, "supporting", "within_delegated_authority")
        outcome = "block_pending_privacy_assessment"
    ctx.facts.update(personal_data=con["processes_personal_data"], total_value=con["annual_value_gbp"] * con["term_months"] / 12)
    _doc(ctx, proc, con, sup, ["New supplier contract for approval", f"Contract {con['contract_number']} - approval request", f"{sup['name']} agreement"],
         [f"Please review and approve the attached agreement with {sup['name']} for {con['title'].lower()}. Annual value is £{con['annual_value_gbp']:,.0f} over {con['term_months']} months.", f"New agreement {con['contract_number']} with {sup['name']} is ready for approval; value £{con['annual_value_gbp']:,.0f} per year."],
         ["A new supplier agreement is ready from our side - could you push it through the process?", "Here's the latest agreement; I'd like it signed this month."])
    ctx.attach(Attachment("Order form summary", [("Counterparty", sup["name"]), ("Annual value", f"£{con['annual_value_gbp']:,.2f}"), ("Term (months)", str(con["term_months"]))], kind=ctx.pick(["md", "scan"])))
    calls = [("get_financial_controls", {"contract_id": con["id"]}, [dau["id"]]), ("get_privacy_assessment", {"contract_id": con["id"]}, [pia["id"]] if pia else [con["id"]]),
             ("get_supplier_risk", {"supplier_id": sup["id"]}, [risk["id"]]), ("get_approval_workflow", {"contract_id": con["id"]}, [wf["id"]]), ("get_contract", {"contract_id": con["id"]}, [con["id"]])]
    _paths(ctx, con, sup, calls)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"New supplier contract approval ({v}).", review_case_type="contract" if outcome != "route_for_standard_approval" else None, extra_relevant=["compare_contract_versions"])


@family("contract_amendment_review", CAT, ["benign_edits", "liability_cap_reduced", "data_processing_removed"])
def contract_amendment_review(ctx: Ctx):
    r, v = ctx.r, ctx.variant
    pd = True if v == "data_processing_removed" else None
    proc, owner, sup, con, vers, dau, risk, wf = _scaffold(ctx, personal_data=pd, n_versions=2, status="in_amendment")
    v1, v2 = vers
    v2["clauses"].update(payment_terms_days=45 if ctx.chance(0.5) else 30, termination_notice_days=r.choice([90, 60]))
    v2["change_summary"] = "Annual renewal amendment: updated notice contact and payment schedule"
    dec = []
    if v == "benign_edits":
        dec.append(ctx.ev(v2, "decisive", "only_administrative_changes")); outcome = "route_for_standard_approval"
    elif v == "liability_cap_reduced":
        v2["clauses"]["liability_cap_gbp"] = r.choice([100_000, 250_000]); con["criticality"] = "critical"
        v2["change_summary"] += "; limitation of liability clause consolidated"
        dec.append(ctx.ev(v2, "decisive", "liability_cap_reduced")); outcome = "request_clause_renegotiation"
    else:
        v2["clauses"]["data_processing_clause"] = False; v2["clauses"]["audit_rights"] = True
        v2["change_summary"] += "; schedule 4 (data protection) removed as superseded"
        dec.append(ctx.ev(v2, "decisive", "data_processing_clause_removed")); ctx.ev(con, "supporting", "processes_personal_data"); outcome = "block_pending_privacy_assessment"
        ctx.add("privacy_assessments", contract_id=con["id"], supplier_id=sup["id"], title="Supplier privacy impact assessment", summary="Assessment relied on the data processing schedule", status="approved", completed_on=day(300), expires_on=future_day(60))
        ctx.records.append(ctx.w.tables["privacy_assessments"][-1]["id"])
    ctx.ev(v1, "supporting", "previous_version", cite=False)
    ctx.facts.update(changed=[k for k in v1["clauses"] if v1["clauses"][k] != v2["clauses"][k]])
    _doc(ctx, proc, con, sup, ["Amended contract for approval", f"{con['contract_number']} renewal amendment", f"Amendment - {sup['name']}"],
         [f"{sup['name']} have sent over the renewal amendment for {con['contract_number']}; they say it's only housekeeping. Please approve.", f"Renewal paperwork for {con['contract_number']} attached - the supplier says changes are minor."],
         ["Renewal paperwork is back from the supplier, they say nothing much has changed. OK to proceed?", "Amendment received - can we sign this week?"])
    ctx.attach(Attachment("Amendment cover note", [("Supplier", sup["name"]), ("Summary of changes", v2["change_summary"].split(";")[0])], kind="scan"))
    calls = [("compare_contract_versions", {"contract_id": con["id"]}, [v2["id"]]), ("get_contract", {"contract_id": con["id"]}, [con["id"]]), ("get_privacy_assessment", {"contract_id": con["id"]}, [p["id"] for p in ctx.w.tables["privacy_assessments"] if p.get("contract_id") == con["id"]]),
             ("get_supplier_risk", {"supplier_id": sup["id"]}, [risk["id"]])]
    _paths(ctx, con, sup, calls)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"Contract amendment ({v}).", review_case_type="contract" if outcome != "route_for_standard_approval" else None, extra_relevant=["get_financial_controls"])


@family("contract_supplier_risk_renewal", CAT, ["risk_elevated", "stale_high_flag_cleared", "screening_pending"])
def contract_supplier_risk_renewal(ctx: Ctx):
    r, v = ctx.r, ctx.variant
    proc, owner, sup, con, vers, dau, risk, wf = _scaffold(ctx, status="renewal")
    risk["status"] = "superseded"; risk["assessed_on"] = day(r.randrange(400, 700))
    dec = []
    if v == "risk_elevated":
        cur = ctx.add("supplier_risk", supplier_id=sup["id"], rating="high", assessed_on=day(r.randrange(5, 40)), status="current", summary="Reassessment after adverse financial indicators", factors=["financial: covenant breach reported", "concentration: high"], sanctions_screening_status="clear", screening_date=day(20))
        dec.append(ctx.ev(cur, "decisive", "current_high_risk")); outcome = "escalate_to_senior_approval"
    elif v == "stale_high_flag_cleared":
        old = ctx.add("supplier_risk", supplier_id=sup["id"], rating="high", assessed_on=day(r.randrange(500, 800)), status="superseded", summary="Initial onboarding assessment: high due to limited trading history", factors=["trading history: short"], sanctions_screening_status="clear", screening_date=day(600))
        cur = ctx.add("supplier_risk", supplier_id=sup["id"], rating="low", assessed_on=day(r.randrange(10, 60)), status="current", summary="Reassessment: three years of stable accounts", factors=["financial: stable"], sanctions_screening_status="clear", screening_date=day(15))
        dec += [ctx.ev(cur, "decisive", "current_low_risk"), ctx.ev(old, "contradicting", "obsolete_high_flag")]; outcome = "route_for_standard_approval"
    else:
        cur = ctx.add("supplier_risk", supplier_id=sup["id"], rating="medium", assessed_on=day(r.randrange(10, 60)), status="current", summary="Reassessment; sanctions screening refresh outstanding", factors=["financial: stable"], sanctions_screening_status="pending", screening_date=day(r.randrange(400, 700)))
        dec.append(ctx.ev(cur, "decisive", "screening_outstanding")); outcome = "request_missing_documents"
    ctx.ev(risk, "context" if risk["id"] not in [e["record_id"] for e in ctx.evidence] else "context", "earlier_assessment", cite=False)
    ctx.facts.update(current_rating=cur["rating"])
    _doc(ctx, proc, con, sup, ["Renewal - supplier risk check", f"{sup['name']} renewal {con['contract_number']}", "Contract renewal due"],
         [f"{con['contract_number']} with {sup['name']} is due for renewal. Please confirm that supplier risk is acceptable before it goes to approval.", f"Renewal of {sup['name']} ({con['contract_number']}): can Risk confirm there is nothing blocking?"],
         ["This one renews next month; I assume it's fine to roll over - can you confirm?", "Renewal coming up and the supplier is chasing; any concerns?"])
    calls = [("get_supplier_risk", {"supplier_id": sup["id"]}, [d for d in dec]), ("get_contract", {"contract_id": con["id"]}, [con["id"]]), ("get_financial_controls", {"contract_id": con["id"]}, [dau["id"]])]
    _paths(ctx, con, sup, calls)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "supplier_fraud"], summary=f"Supplier risk at renewal ({v}).", review_case_type="contract" if outcome == "escalate_to_senior_approval" else None, extra_relevant=["get_approval_workflow", "get_privacy_assessment"])


@family("contract_retrospective_approval", CAT, ["executed_without_approval", "approval_unlinked", "signatory_evidence_missing"])
def contract_retrospective_approval(ctx: Ctx):
    r, v = ctx.r, ctx.variant
    proc, owner, sup, con, vers, dau, risk, wf = _scaffold(ctx, status="executed")
    con["signed_on"] = day(r.randrange(3, 20))
    dec = []
    if v == "executed_without_approval":
        wf["status"] = "rejected"; wf["steps"] = [{"role": "Procurement Lead", "status": "approved"}, {"role": "Legal", "status": "rejected"}]; wf["started_on"] = day(30)
        dec += [ctx.ev(wf, "decisive", "approval_not_completed_before_signature"), ctx.ev(con, "decisive", "contract_already_executed")]; outcome = "escalate_to_senior_approval"
    elif v == "approval_unlinked":
        old = ctx.add("contracts", **{**{k: val for k, val in con.items() if k != "id"}, "status": "superseded", "title": con["title"] + " (draft)", "current_version_id": None})
        wf["contract_id"] = old["id"]; wf["status"] = "completed"; wf["steps"] = [{"role": "Procurement Lead", "status": "approved"}, {"role": "Legal", "status": "approved"}]; wf["started_on"] = day(60)
        dec += [ctx.ev(wf, "decisive", "approval_completed_on_earlier_draft"), ctx.ev(old, "decisive", "workflow_linked_to_earlier_draft")]; outcome = "route_for_standard_approval"
        ctx.facts["unlinked_to"] = old["id"]
    else:
        wf["status"] = "completed"; wf["steps"] = [{"role": "Procurement Lead", "status": "approved"}, {"role": "Legal", "status": "approved"}]; wf["started_on"] = day(40)
        evd = ctx.w.get(con["signatory_evidence_id"]); evd["status"] = "missing"; evd["text"] = "Signature page not uploaded"; con["signatory_evidence_status"] = "missing"
        dec += [ctx.ev(evd, "decisive", "signature_evidence_missing"), ctx.ev(wf, "supporting", "approval_completed")]; outcome = "request_missing_documents"
    ctx.facts.update(signed_on=con["signed_on"])
    _doc(ctx, proc, con, sup, ["Contract signed - please update records", f"{con['contract_number']} executed", "Retrospective approval check"],
         [f"{con['contract_number']} with {sup['name']} was signed on {ctx.dt(con['signed_on'])}. Please check the approval trail is in order and record it.", f"We've executed {con['contract_number']} ({sup['name']}); could Contracts confirm approvals are on file?"],
         ["That agreement got signed last week - can someone make sure the paperwork is all filed correctly?", "Signed copy done; just need the approvals tidied up."])
    calls = [("get_approval_workflow", {"contract_id": con["id"]}, [wf["id"]] if v != "approval_unlinked" else []), ("get_contract", {"contract_id": con["id"]}, [con["id"]]), ("get_financial_controls", {"contract_id": con["id"]}, [dau["id"]])]
    _paths(ctx, con, sup, calls)
    if v == "approval_unlinked":
        ctx.path([old["id"], wf["id"]], *_entry(con), ("get_approval_workflow", {"contract_id": old["id"]}))
    if v == "signatory_evidence_missing":
        ctx.path([evd["id"]], *_entry(con), ("get_linked_records", {"record_id": con["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"Retrospective approval check ({v}).", review_case_type="contract" if outcome.startswith("escalate") else None, extra_relevant=["compare_contract_versions", "get_supplier_risk"])
