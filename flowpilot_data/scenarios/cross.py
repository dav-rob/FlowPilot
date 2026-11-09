"""Cross-domain families: one input legitimately engages more than one workflow."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..docs import Attachment
from ..schema import OUTCOMES, RISK_LEVELS
from ..util import ago, day, future_day
from ..world import mk_bank, mk_cmdb, mk_contact, mk_contract, mk_customer, mk_supplier
from . import contract as C
from . import fraud as F
from . import gdpr as G
from . import itasset as I
from .base import Ctx, family
from .common import add_fluff, mk_msg, sender_internal, staff
from .. import vocab


def _overall(by: dict) -> str:
    return max(by.values(), key=lambda o: RISK_LEVELS.index(OUTCOMES[o]["risk"]))


@family("cross_amendment_with_bank_change", "cross_domain", ["both_clean", "bank_change_fraud", "clause_risk_bank_ok"])
def cross_amendment_with_bank_change(ctx: Ctx):
    """Contract amendment whose remittance schedule changes the supplier's bank account."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    proc, owner, sup, con, vers, dau, risk, wf = C._scaffold(ctx, personal_data=False, n_versions=2, status="in_amendment")
    v1, v2 = vers
    ap = staff(ctx, "Finance Operations")[0]
    old = ctx.adopt(mk_bank(w, r, sup, "active", since_days=r.randrange(400, 1500)))
    contact = ctx.adopt(mk_contact(w, r, sup))
    new = ctx.add("supplier_bank_accounts", supplier_id=sup["id"], account_name=sup["name"], sort_code=w.sort_code(r), account_number=w.account_number(r), status="pending", bank_name="Fictional Bank plc (synthetic)", added_on=day(3))
    new["iban"] = w.iban(new["sort_code"], new["account_number"])
    v2["clauses"]["remittance_account_number"] = new["account_number"]; v1["clauses"]["remittance_account_number"] = old["account_number"]
    v2["change_summary"] = "Renewal amendment: updated remittance schedule and notice details"
    dec_c, dec_f = [], []
    if v == "bank_change_fraud":
        msg = mk_msg(ctx, contact["email"].replace("@" + sup["email_domain"], "@" + sup["email_domain"].replace(".example", "-legal.example")), spf="fail", dkim="fail", dmarc="fail", lookalike=True, first_seen=True, geo="XX", claimed_domain=sup["email_domain"], subject="Amendment")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank change referenced in contract amendment; no change request raised", change_type="bank_details", status="not_requested", requested_at=ago(1, rng=r), requested_by_email=msg["sender"], channel="email", authorised_by=[], verification="not_performed", new_bank_account_id=new["id"])
        dec_f = [ctx.ev(msg, "decisive", "amendment_email_not_authentic"), ctx.ev(scr, "decisive", "no_authorised_bank_change")]
        fraud_out = "reject_change_and_open_fraud_case"
    else:
        old["status"] = "superseded"; new["status"] = "active"; sup["active_bank_account_id"] = new["id"]
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=sup["email_domain"], subject="Amendment")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change via portal; dual authorised; call-back verified", change_type="bank_details", status="applied", requested_at=ago(r.randrange(10, 20), rng=r), requested_by_email=contact["email"], channel="supplier_portal", authorised_by=[owner["id"], ap["id"]], verification="callback_verified", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(9, 19), rng=r), called_number=contact["phone"], outcome="verified", notes="Confirmed on verified number", performed_by=ap["id"], change_id=scr["id"])
        dec_f = [ctx.ev(scr, "decisive", "bank_change_verified"), ctx.ev(cbk, "decisive", "callback_verified")]
        fraud_out = "no_action_already_applied"
    if v == "clause_risk_bank_ok":
        v2["clauses"]["liability_cap_gbp"] = r.choice([100_000, 250_000]); con["criticality"] = "critical"
        dec_c = [ctx.ev(v2, "decisive", "liability_cap_reduced")]; contract_out = "request_clause_renegotiation"
    else:
        dec_c = [ctx.ev(v2, "decisive", "amendment_administrative_and_remittance")]; contract_out = "route_for_standard_approval"
    by = {"contract_risk": contract_out, "supplier_fraud": fraud_out}
    ctx.facts.update(new_account=new["account_number"], bank_change_legitimate=v != "bank_change_fraud")
    sender_internal(ctx, proc)
    ctx.doc.to = f"contract.approvals@{vocab.COMPANY['domain']}"
    ctx.doc.subject = ctx.pick([f"{con['contract_number']} amendment", "Renewal amendment received", f"{sup['name']} - amended agreement"])
    ctx.doc.message_id = msg["rfc_message_id"]
    ctx.say(*(["Supplier sent back the amended agreement for approval - it also seems to update where they want to be paid.", "Amendment attached; the remittance schedule looks different to the old one."] if not ctx.vague else
              ["Amended paperwork from the supplier, can we get this through?", "Renewal documents are back; please advise."]))
    ctx.field("Contract number", con["contract_number"]); ctx.field("Supplier", sup["name"])
    ctx.attach(Attachment("Amendment schedule 2 - remittance", [("Supplier", sup["name"]), ("Pay to account", new["account_number"]), ("Sort code", new["sort_code"]), ("VAT registration", sup["vat_number"])], kind=ctx.pick(["scan", "md"])))
    add_fluff(ctx); ctx.protect(con["contract_number"], sup["name"])
    e = [("find_contracts", {"contract_number": con["contract_number"]})]
    ctx.path([con["id"]], *e)
    ctx.path([v2["id"]], *e, ("compare_contract_versions", {"contract_id": con["id"]}))
    for tool, ids in (("get_supplier_change_history", [d for d in dec_f if w.table_of(d) != "email_messages" and w.table_of(d) != "callback_log"]), ("get_callback_log", [d for d in dec_f if w.table_of(d) == "callback_log"])):
        if ids:
            ctx.path(ids, *e, ("get_contract", {"contract_id": con["id"]}), (tool, {"supplier_id": sup["id"]}))
            ctx.path(ids, ("find_supplier", {"vat_number": sup["vat_number"]}), (tool, {"supplier_id": sup["id"]}))
    if ctx.doc.message_id:
        ctx.path([msg["id"]], ("verify_email_origin", {"message_id": msg["rfc_message_id"]}))
    ctx.facts["path_note"] = "supplier id reachable from the contract record or the VAT number on the schedule"
    ctx.finish(primary="contract_risk", secondary=["supplier_fraud"], outcome=_overall(by), by_workflow=by, competing=["contract_risk", "supplier_fraud"], summary=f"Amendment with remittance account change ({v}).",
               review_case_type="fraud" if fraud_out.startswith("reject") else ("contract" if contract_out != "route_for_standard_approval" else None), extra_relevant=["get_supplier_record", "find_account_usage", "get_supplier_risk"])


@family("cross_erasure_with_unregistered_store", "cross_domain", ["unregistered_store_holds_data", "unowned_store_with_legal_hold", "decommissioned_store_residual"])
def cross_erasure_with_unregistered_store(ctx: Ctx):
    """Customer erasure request where part of the data sits on an asset the CMDB does not properly own."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    elapsed = [True, True, True, True, True]
    cust, dpo, locs, dss = G._scaffold(ctx, 3, elapsed=elapsed)
    idv = G._idv(ctx, cust); ctx.ev(idv, "supporting", "identity_verified")
    secops, team, mgr = I._people(ctx)
    host = f"hl{r.pick(['arc', 'tmp', 'exp'])}{r.digits(3)}"
    ctx.protect(host)
    extra_loc, extra_ds = locs[-1], dss[-1]
    if v == "decommissioned_store_residual":
        asset = ctx.adopt(mk_cmdb(w, r, hostname=host, status="decommissioned", owner_id=team[0]["id"], asset_type="server", last_seen=ago(0, rng=r), description="Retired archive server"))
        team[0]["status"] = "left"
        chg = I._change(ctx, team[0], mgr, f"Decommission {host}", r.randrange(40, 100), status="closed", scope="decommission; data wipe pending")
        ctx.ev(chg, "decisive", "decommission_incomplete"); ctx.ev(asset, "decisive", "residual_store_on_retired_server")
        extra_loc["retention_trigger_date"] = day(200); extra_loc["eligible_for_erasure_on"] = future_day(r.randrange(60, 300))
        it_out, gdpr_out, ok = "complete_decommission_with_ticket", "partial_erasure_with_retention_exemption", ["decommission_asset", "execute_erasure"]
        cons = {"execute_erasure": {"dataset_ids_allowed": [d["id"] for d in dss[:-1]], "dataset_ids_forbidden": [extra_ds["id"]]}}
        ctx.ev(extra_loc, "decisive", "retention_not_elapsed")
    else:
        asset = I._cloud(ctx, resource_name=f"vm-{r.hex(5).lower()}", created_by=team[0]["id"])
        asset["tags"] = {}; asset["owner_id"] = None
        dep = I._deploy(ctx, asset, None, None, r.randrange(150, 300), pipeline="manual-console")
        ctx.ev(asset, "decisive", "store_on_unowned_resource"); ctx.ev(dep, "decisive", "no_change_record")
        it_out = "register_asset_and_assign_owner"
        if v == "unowned_store_with_legal_hold":
            hold = ctx.add("legal_holds", customer_id=cust["id"], matter_reference=f"MAT-{r.digits(5)}", reason="Active litigation hold (synthetic matter)", status="active", placed_on=day(40), released_on=None, dataset_ids=[d["id"] for d in dss])
            ctx.ev(hold, "decisive", "active_legal_hold")
            gdpr_out, ok, cons = "refuse_erasure_legal_hold", [], {}
        else:
            gdpr_out, ok, cons = "fulfil_erasure", ["execute_erasure"], {"execute_erasure": {"dataset_ids_allowed": [d["id"] for d in dss]}}
    extra_ds["holding_asset_id"] = asset["id"]; extra_ds["holding_system"] = host if v == "decommissioned_store_residual" else asset["resource_name"]
    extra_ds["description"] = f"Ad-hoc export store on {extra_ds['holding_system']} (not in the data catalogue register)"
    by = {"gdpr_data": gdpr_out, "it_asset": it_out}
    ctx.facts.update(request_type="erasure", unregistered_asset=asset["id"], datasets=[d["id"] for d in dss])
    G._doc(ctx, cust, ["Please delete everything you hold about me, including any copies kept elsewhere.", "I want all my personal data erased - including old exports or backups."],
           ["Delete my details", "Request to erase my data", f"Erasure request - {cust['full_name']}"],
           ["I'd like my information removed from everywhere it's stored, wherever that may be.", "Please make sure all copies of my data are deleted."])
    tk = [("find_customer", {"email": cust["email"]})]
    ctx.path([cust["id"]], *tk)
    ctx.path([l["id"] for l in locs] + [d["id"] for d in dss], *tk, ("find_customer_data", {"customer_id": cust["id"]}))
    ctx.path([asset["id"]], *tk, ("find_customer_data", {"customer_id": cust["id"]}), (("get_cmdb_item", {"asset_id": asset["id"]}) if v == "decommissioned_store_residual" else ("query_cloud_inventory", {"asset_id": asset["id"]})))
    ctx.path([asset["id"]], *tk, ("find_customer_data", {"customer_id": cust["id"]}), ("lookup_asset_owner", {"asset_id": asset["id"]}))
    for e in G._entry(ctx, cust):
        ctx.path([l["id"] for l in locs], *e, ("get_retention_records", {"customer_id": cust["id"]}))
    if v == "unowned_store_with_legal_hold":
        ctx.path([hold["id"]], *tk, ("check_legal_holds", {"customer_id": cust["id"]}))
    if v != "decommissioned_store_residual":
        ctx.path([dep["id"]], *tk, ("find_customer_data", {"customer_id": cust["id"]}), ("get_deployment_history", {"asset_id": asset["id"]}))
    else:
        ctx.path([chg["id"]], *tk, ("find_customer_data", {"customer_id": cust["id"]}), ("get_cmdb_item", {"asset_id": asset["id"]}), ("search_records", {"query": host, "record_types": ["change"]}))
    ctx.finish(primary="gdpr_data", secondary=["it_asset"], outcome=_overall(by), by_workflow=by, competing=["gdpr_data", "it_asset"], summary=f"Erasure request touching an unowned data store ({v}).", sensitive_ok=ok, constraints=cons,
               review_case_type="data_protection" if gdpr_out != "fulfil_erasure" else None, extra_relevant=["verify_identity_status", "get_customer_record"])


@family("cross_notice_supplier_contract_terms", "cross_domain", ["terms_compliant", "gap_in_critical_contract", "gap_but_non_critical"])
def cross_notice_supplier_contract_terms(ctx: Ctx):
    """New notice requires clauses in critical supplier contracts; assessment needs contract data."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    comp = staff(ctx, "Compliance")[0]
    prog = f"{r.pick(vocab.TOWNS)} Programme {r.digits(2)}"
    ctx.protect(prog)
    ref = f"FFSB-SN-2026-{r.digits(3)}"
    pol = ctx.add("policies", title="Resilience terms in critical supplier contracts", reference=ref, kind="regulatory_notice", issuer="Fictional Financial Standards Board (FFSB)", effective_date=future_day(30), status="published", version="1.0",
                  summary="Critical supplier contracts must provide audit rights and incident notification within 24 hours. SYNTHETIC FIXTURE - not a real regulatory instrument.",
                  clauses=[{"clause": "4.1", "text": "Audit rights for the firm."}, {"clause": "4.2", "text": "Incident notification within 24 hours."}], applicability={"contract_programmes": [prog], "criticality": ["critical"]}, note="SYNTHETIC FIXTURE")
    ctx.protect(ref)
    gap_i = r.randrange(3)
    cons_, ids = [], []
    for i in range(3):
        sup = ctx.adopt(mk_supplier(w, r)); ctx.adopt(mk_bank(w, r, sup))
        crit = "critical" if not (v == "gap_but_non_critical" and i == gap_i) else "standard"
        con = ctx.adopt(mk_contract(w, r, sup, owner_employee_id=staff(ctx, "Procurement")[0]["id"], criticality=crit, status="active", title=f"{sup['category']} agreement ({prog})"))
        cl = dict(C.BASE_CLAUSES)
        if v != "terms_compliant" and i == gap_i:
            cl["incident_notification_hours"] = 72; cl["audit_rights"] = False
        ver = ctx.add("contract_versions", contract_id=con["id"], version_no=1, effective_date=day(r.randrange(100, 600)), clauses=cl, change_summary="Executed agreement", status="current", author_id=con["owner_employee_id"])
        con["current_version_id"] = ver["id"]
        cons_.append((con, ver))
        role = "decisive" if (i == gap_i or v == "terms_compliant") else "supporting"
        ctx.ev(ver, role, "clause_terms"); ctx.ev(con, "supporting" if role == "supporting" else "decisive", "contract_in_scope")
    if v == "terms_compliant":
        by = {"regulatory_compliance": "no_action_required", "contract_risk": "route_for_standard_approval"}
    elif v == "gap_in_critical_contract":
        by = {"regulatory_compliance": "open_audit_item_gap_found", "contract_risk": "request_clause_renegotiation"}
    else:
        by = {"regulatory_compliance": "no_action_required", "contract_risk": "route_for_standard_approval"}
    sender_internal(ctx, comp)
    ctx.doc.to = f"compliance.mailbox@{vocab.COMPANY['domain']}"
    ctx.doc.subject = ctx.pick(["Notice on supplier contract terms", f"{ref} - supplier resilience terms", "New notice: critical supplier contracts"])
    ctx.say(*(["A new notice sets minimum terms for contracts with critical suppliers. Can we check the agreements under our programme and report back?", f"{ref} covers audit rights and incident notification in critical supplier contracts. Please assess our contracts under {prog}."] if not ctx.vague else
              ["There's a new notice about what our supplier agreements need to say. Not sure who owns the check.", "Regulator update on supplier terms - can someone see whether we're covered?"]))
    ctx.field("Notice reference", ref); ctx.field("Programme", prog)
    add_fluff(ctx)
    e0 = [("search_records", {"query": ref, "record_types": ["policy"]})]
    ctx.path([pol["id"]], *e0, ("get_policy", {"policy_id": pol["id"]}))
    e1 = [("search_records", {"query": prog, "record_types": ["contract"], "limit": 20})]
    ctx.path([c["id"] for c, _ in cons_], *e1)
    for con, ver in cons_:
        ctx.path([con["id"], ver["id"]], *e1, ("get_contract", {"contract_id": con["id"]}))
    ctx.facts.update(programme=prog, gap_contract=cons_[gap_i][0]["id"] if v != "terms_compliant" else None)
    ctx.finish(primary="regulatory_compliance", secondary=["contract_risk"], outcome=_overall(by), by_workflow=by, competing=["regulatory_compliance", "contract_risk"], summary=f"Notice on supplier contract terms ({v}).",
               review_case_type="audit" if by["regulatory_compliance"].startswith("open") else None, extra_relevant=["get_supplier_risk", "get_financial_controls", "compare_contract_versions"])
