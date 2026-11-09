"""Data-subject request families (CRM / identity / data catalogue / retention / legal holds). Rules are synthetic fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..docs import Attachment
from ..util import REFERENCE_NOW, ago, day, future_day
from ..world import mk_customer, slug
from .base import Ctx, family
from .common import add_fluff, staff
from .. import vocab

CAT = "gdpr_data"
DS_SPECS = [("Savings ledger", "Savings Core", ["identity", "transactions"], 2190), ("Marketing preferences", "Campaign Hub", ["contact", "preferences"], 365),
            ("Call recordings", "Contact Centre Archive", ["voice", "identity"], 730), ("Statements archive", "Statements Store", ["transactions", "address"], 1095),
            ("Complaints log", "Case Workbench", ["identity", "correspondence"], 1460)]


def _scaffold(ctx: Ctx, n_ds: int = 3, cust_over=None, elapsed=(True,) * 5, hold_released=True):
    w, r = ctx.w, ctx.r
    cust = ctx.adopt(mk_customer(w, r, **(cust_over or {})))
    ctx.protect(cust["full_name"])
    dpo = staff(ctx, "Data Protection Office")[0]
    ctx.add("customer_products", customer_id=cust["id"], product_name=r.pick(vocab.PRODUCTS), account_reference=f"ACC{r.digits(8)}", status="open", opened_on=day(r.randrange(200, 2000)))
    specs = r.sample(DS_SPECS, n_ds)
    locs, dss = [], []
    for k, (nm, sysname, cats, days) in enumerate(specs):
        rule = ctx.add("retention_rules", rule_name=f"{nm} retention (synthetic schedule)", retention_days=days, trigger="end_of_relationship", basis="synthetic retention fixture; not a legal statement")
        ds = ctx.add("datasets", name=f"{nm} - {w.rng.pick(['v1', 'v2', 'legacy'])}", description=f"{sysname} dataset holding {', '.join(cats)} data", holding_system=sysname, data_categories=cats, retention_rule_id=rule["id"])
        trigger = day(days + r.randrange(10, 60) if elapsed[k] else days - r.randrange(100, 300))
        elig = (datetime.strptime(trigger, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d") if False else None
        # eligibility date = trigger date + retention days; elapsed means it lies in the past
        t0 = datetime.strptime(trigger, "%Y-%m-%d"); elig = (t0 + timedelta(days=days)).strftime("%Y-%m-%d")
        loc = ctx.add("data_locations", customer_id=cust["id"], dataset_id=ds["id"], record_locator=f"{ds['id']}/{cust['customer_reference']}", record_count=r.randrange(3, 400), retention_trigger_date=trigger, eligible_for_erasure_on=elig)
        locs.append(loc); dss.append(ds)
        ctx.ev(ds, "context", "dataset_holding_customer_data", cite=False)
    if hold_released:  # parity: every customer has an old, released hold on a different matter
        ctx.add("legal_holds", customer_id=cust["id"], matter_reference=f"MAT-{r.digits(5)}", reason="Closed dispute (synthetic)", status="released", placed_on=day(r.randrange(500, 900)), released_on=day(r.randrange(200, 450)), dataset_ids=[])
    ctx.add("data_requests", customer_id=cust["id"], request_reference=f"DSR-{r.digits(5)}", summary="Marketing preference change", request_type="preference", status="closed", received_on=day(r.randrange(120, 600)), outcome="completed")
    if ctx.conflicting:  # namesake customer with a similar name
        twin = ctx.adopt(mk_customer(w, r, full_name=cust["full_name"], postcode=w.postcode(r), date_of_birth=f"{r.randrange(1948, 2002)}-0{r.randrange(1, 9)}-1{r.randrange(0, 9)}", email=w.unique_email(slug(cust['full_name']).replace('-', '.') + "1", r)))
        ctx.facts["namesake_customer"] = twin["id"]; ctx.mark_conflict()
    return cust, dpo, locs, dss


def _idv(ctx, cust, status="passed", method="document_and_selfie", checked_days=10, valid_days=355):
    return ctx.add("identity_verifications", customer_id=cust["id"], method=method, outcome=status, checked_on=day(checked_days), expires_on=future_day(valid_days) if valid_days >= 0 else day(-valid_days), request_reference=None)


def _doc(ctx: Ctx, cust, kind_text, subject_alts, vague, extra_fields=(), sender_name=None, to="dataprotection@"):
    r = ctx.r
    ctx.doc.sender = f"{sender_name or cust['full_name']} <{cust['email']}>"
    ctx.doc.to = to + vocab.COMPANY["domain"]
    ctx.doc.subject = ctx.pick(subject_alts)
    ctx.doc.signature = sender_name or cust["full_name"]
    if ctx.vague:
        ctx.say(*vague)
    else:
        ctx.say(*kind_text)
    ctx.field("Name", cust["full_name"]); ctx.field("Email", cust["email"])
    for a, b in extra_fields:
        ctx.field(a, b)
    ctx.maybe_field("Customer reference", cust["customer_reference"])
    add_fluff(ctx)


def _entry(ctx: Ctx, cust):
    """Valid entry steps resolving the customer id from document-visible identifiers."""
    e = [[("find_customer", {"email": cust["email"]})]]
    if any(a == "Customer reference" for a, _ in ctx.doc.fields):
        e.append([("find_customer", {"customer_reference": cust["customer_reference"]})])
    toks = set(cust["full_name"].lower().split())
    if sum(1 for c in ctx.w.tables["customers"] if any(toks <= set(n.lower().split()) for n in [c["full_name"]] + c.get("previous_names", []))) == 1:
        e.append([("find_customer", {"full_name": cust["full_name"]})])
    return e


def _paths(ctx: Ctx, cust, tools: dict):
    for e in _entry(ctx, cust):
        ctx.path([cust["id"]], *e)
        for tool, ids in tools.items():
            ctx.path(ids, *e, (tool, {"customer_id": cust["id"]}))


@family("gdpr_erasure_request", CAT, ["eligible_erase", "legal_hold_blocks", "retention_active_partial"])
def gdpr_erasure_request(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    n = 3
    elapsed = [True, True, True, True, True]
    if v == "retention_active_partial":
        elapsed[r.randrange(n)] = False
    cust, dpo, locs, dss = _scaffold(ctx, n, elapsed=elapsed)
    idv = _idv(ctx, cust)
    ctx.ev(idv, "supporting", "identity_verified")
    hold = None
    if v == "legal_hold_blocks":
        hold = ctx.add("legal_holds", customer_id=cust["id"], matter_reference=f"MAT-{r.digits(5)}", reason="Active litigation hold (synthetic matter)", status="active", placed_on=day(r.randrange(20, 200)), released_on=None, dataset_ids=[d["id"] for d in dss])
        dec = [ctx.ev(hold, "decisive", "active_legal_hold")]
        outcome, ok, cons = "refuse_erasure_legal_hold", [], {}
    elif v == "retention_active_partial":
        idx = [i for i, e in enumerate(elapsed[:n]) if not e][0]
        dec = [ctx.ev(locs[idx], "decisive", "retention_not_elapsed"), ctx.ev(dss[idx], "decisive", "dataset_retention_rule")]
        allowed = [d["id"] for i, d in enumerate(dss) if i != idx]
        outcome, ok, cons = "partial_erasure_with_retention_exemption", ["execute_erasure"], {"execute_erasure": {"dataset_ids_allowed": allowed, "dataset_ids_forbidden": [dss[idx]["id"]]}}
        for i, l in enumerate(locs):
            if i != idx: ctx.ev(l, "supporting", "retention_elapsed", cite=False)
    else:
        dec = [ctx.ev(l, "decisive", "retention_elapsed") for l in locs]
        outcome, ok, cons = "fulfil_erasure", ["execute_erasure"], {"execute_erasure": {"dataset_ids_allowed": [d["id"] for d in dss]}}
    _doc(ctx, cust, ["I am writing to ask that you delete all of the personal data you hold about me. I closed my accounts some time ago.", "Please erase my personal information from your systems. I no longer wish to be a customer."],
         ["Delete my details", "Request to erase my data", f"Data erasure request - {cust['full_name']}"],
         ["I'd like my information removed from wherever you keep it, please let me know when that's done.", "Following my account closure I would like everything about me wiped - not sure what you hold."])
    ctx.attach(Attachment("Customer request form", [("Request type", "Erasure"), ("Customer", cust["full_name"]), ("Date", ctx.dt(day(1)))], kind="scan")) if ctx.chance(0.4) else None
    tools = {"find_customer_data": [l["id"] for l in locs] + [d["id"] for d in dss], "get_retention_records": [l["id"] for l in locs] + [d["id"] for d in dss], "check_legal_holds": [hold["id"]] if hold else [], "verify_identity_status": [idv["id"]]}
    _paths(ctx, cust, {k: v2 for k, v2 in tools.items() if v2})
    ctx.facts.update(request_type="erasure", datasets=[d["id"] for d in dss])
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "contract_risk"], summary=f"Customer erasure request ({v}).", sensitive_ok=ok, constraints=cons, review_case_type="data_protection" if outcome.startswith(("refuse", "partial")) else None,
               extra_relevant=["get_customer_record", "get_data_request_history"])


@family("gdpr_access_request", CAT, ["verified_fulfil", "identity_unverified", "third_party_no_authority"])
def gdpr_access_request(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    cust, dpo, locs, dss = _scaffold(ctx, 3)
    third = None
    req_name = None
    if v == "verified_fulfil":
        idv = _idv(ctx, cust); dec = [ctx.ev(idv, "decisive", "identity_verified_current")]
        outcome, ok, cons = "fulfil_access_request", ["export_customer_data"], {"export_customer_data": {"dataset_ids_allowed": [d["id"] for d in dss]}}
    elif v == "identity_unverified":
        idv = _idv(ctx, cust, status=r.choice(["failed", "pending"]) if not ctx.conflicting else "passed", method="knowledge_questions", checked_days=r.randrange(400, 700) if ctx.conflicting else 3, valid_days=-r.randrange(20, 300) if ctx.conflicting else 5)
        dec = [ctx.ev(idv, "decisive", "identity_not_verified_or_expired")]
        outcome, ok, cons = "request_identity_verification", [], {}
    else:
        idv = _idv(ctx, cust)
        req_name = f"{r.pick(vocab.FIRST)} {r.pick(vocab.LAST)}"
        third = ctx.add("authority_letters", customer_id=cust["id"], signatory=req_name if not ctx.conflicting else cust["full_name"], granted_to=req_name, summary="Letter of authority to obtain copies of personal data (synthetic)", received_on=day(r.randrange(300, 700)), valid_until=day(r.randrange(30, 250)), scope="subject access only")
        dec = [ctx.ev(third, "decisive", "authority_expired_or_invalid"), ctx.ev(idv, "supporting", "customer_identity_verified")]
        outcome, ok, cons = "reject_third_party_request", [], {}
    if v != "third_party_no_authority":
        pass
    ctx.facts.update(request_type="access", requester_is_customer=req_name is None)
    ctx.doc.protect.add((req_name or "").lower())
    _doc(ctx, cust, ["Please send me a copy of all the personal data you hold about me." if not req_name else f"I act for {cust['full_name']} and request a copy of all personal data held about them. A letter of authority is attached.",
                     "I would like to make a subject access request for everything you hold on me." if not req_name else f"On behalf of my client {cust['full_name']} please supply their personal data. Authority attached."],
         ["Subject access request", "Request for copy of my data", f"Access request - {cust['full_name']}"],
         ["Could you let me know what information you have about me and send it over?", "I'd like to see what you hold - please advise how to proceed."],
         sender_name=req_name)
    if req_name:
        ctx.attach(Attachment("Letter of authority", [("Client", cust["full_name"]), ("Authorised party", req_name), ("Dated", ctx.dt(third["received_on"]))], kind="scan"))
        ctx.doc.sender = f"{req_name} <{req_name.split()[0].lower()}.{req_name.split()[-1].lower()}@advice-partners.example>"
    tools = {"verify_identity_status": [idv["id"]], "find_customer_data": [d["id"] for d in dss], "get_data_request_history": [], "get_third_party_authority": [third["id"]] if third else []}
    _paths(ctx, cust, {k: x for k, x in tools.items() if x})
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "contract_risk"], summary=f"Subject access request ({v}).", sensitive_ok=ok, constraints=cons, review_case_type="data_protection" if outcome.startswith("reject") else None,
               extra_relevant=["get_customer_record", "check_legal_holds", "get_third_party_authority"])


@family("gdpr_correction_request", CAT, ["valid_correction", "conflicting_records", "account_takeover_suspected"])
def gdpr_correction_request(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    cust, dpo, locs, dss = _scaffold(ctx, 2)
    new_addr = f"{r.randrange(1, 90)} {r.pick(vocab.STREETS)}, {r.pick(vocab.TOWNS)} {w.postcode(r)}"
    emp = staff(ctx, "Customer Operations")[0]
    dec = []
    if v == "valid_correction":
        idv = _idv(ctx, cust)
        proof = ctx.add("data_requests", customer_id=cust["id"], request_reference=f"DSR-{r.digits(5)}", summary="Proof of address (utility bill) received and verified", request_type="evidence", status="closed", received_on=day(r.randrange(2, 9)), outcome="evidence_verified", proposed_address=new_addr)
        dec += [ctx.ev(proof, "decisive", "proof_of_address_verified"), ctx.ev(idv, "decisive", "identity_verified")]
        outcome, ok, cons = "apply_correction", ["update_customer_record"], {"update_customer_record": {"customer_id": cust["id"]}}
    elif v == "conflicting_records":
        idv = _idv(ctx, cust)
        kyc = ctx.add("data_requests", customer_id=cust["id"], request_reference=f"DSR-{r.digits(5)}", summary="KYC refresh recorded a different verified address; no proof supplied for requested change", request_type="kyc", status="open", received_on=day(r.randrange(5, 30)), outcome="pending_evidence", verified_address=cust["address"])
        dec += [ctx.ev(kyc, "decisive", "kyc_address_conflicts_no_proof"), ctx.ev(idv, "supporting", "identity_verified")]
        outcome, ok, cons = "request_supporting_evidence", [], {}
    else:
        idv = _idv(ctx, cust, status="failed", method="knowledge_questions", checked_days=1, valid_days=5)
        l1 = ctx.add("audit_log", subject_id=cust["id"], summary="Email address changed on customer profile", actor="online-banking", timestamp=ago(2, rng=r), action="update", device="new_device")
        l2 = ctx.add("audit_log", subject_id=cust["id"], summary="Mobile number changed on customer profile", actor="online-banking", timestamp=ago(2, hours=-1, rng=r), action="update", device="new_device")
        dec += [ctx.ev(l1, "decisive", "recent_contact_changes_new_device"), ctx.ev(l2, "decisive", "recent_contact_changes_new_device"), ctx.ev(idv, "decisive", "identity_check_failed")]
        outcome, ok, cons = "refer_to_security_review", [], {}
    ctx.facts.update(request_type="correction", requested_address=new_addr)
    _doc(ctx, cust, [f"Please update my address on your records to: {new_addr}.", f"I have moved house. Could you change the address you hold for me to {new_addr}?"],
         ["Change of address", "Please correct my details", f"Update my records - {cust['full_name']}"],
         ["Some of the details you have for me are out of date and I would like them corrected, as set out below.", "My information on your system is wrong - please fix it."],
         extra_fields=[("New address", new_addr)])
    if ctx.chance(0.5):
        ctx.attach(Attachment("Utility bill (scan)", [("Account holder", cust["full_name"]), ("Service address", new_addr), ("Bill date", ctx.dt(day(12)))], kind="scan"))
    tools = {"verify_identity_status": [idv["id"]], "get_data_request_history": [d for d in dec if w.table_of(d) == "data_requests"], "get_audit_trail": [d for d in dec if w.table_of(d) == "audit_log"]}
    for e in _entry(ctx, cust):
        ctx.path([cust["id"]], *e)
        for tool, ids in tools.items():
            if ids:
                ctx.path(ids, *e, (tool, {"customer_id": cust["id"]}) if tool != "get_audit_trail" else (tool, {"record_id": cust["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "supplier_fraud"], summary=f"Customer asks to correct personal data ({v}).", sensitive_ok=ok, constraints=cons, review_case_type="data_protection" if outcome.startswith("refer") else None,
               extra_relevant=["get_customer_record", "find_customer_data"])


@family("gdpr_ambiguous_requester", CAT, ["resolved_by_identifiers", "unresolvable_ambiguity", "no_record_found"])
def gdpr_ambiguous_requester(ctx: Ctx):
    """Requester identity is only partly stated; resolution depends on matching customer records."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    cust, dpo, locs, dss = _scaffold(ctx, 2)
    ctx.facts.pop("namesake_customer", None)
    name = cust["full_name"]
    twin = ctx.adopt(mk_customer(w, r, full_name=name, postcode=w.postcode(r), date_of_birth=f"{r.randrange(1948, 2002)}-0{r.randrange(1, 9)}-2{r.randrange(0, 8)}", email=w.unique_email(slug(name).replace('-', '.') + "1", r)))
    ctx.facts["namesake_customer"] = twin["id"]
    idv = _idv(ctx, cust)
    pc_in_doc = v == "resolved_by_identifiers"
    ctx.doc.sender = f"{name} <{'unknown.sender' if v != 'resolved_by_identifiers' else slug(name).replace('-', '.') + '.alt'}@mail.example>"
    ctx.doc.to = "dataprotection@" + vocab.COMPANY["domain"]; ctx.doc.signature = name
    ctx.doc.subject = ctx.pick(["Request for my information", "What data do you hold on me?", f"Data request from {name}"])
    if v == "no_record_found":
        ghost = f"{r.pick(vocab.FIRST)} {r.pick(vocab.LAST)}"
        taken = {c["full_name"].lower() for c in w.tables["customers"]} | {pn.lower() for c in w.tables["customers"] for pn in c.get("previous_names", [])}
        while ghost.lower() in taken:
            ghost = f"{r.pick(vocab.FIRST)} {r.pick(vocab.LAST)}"
        ctx.doc.sender = f"{ghost} <{slug(ghost).replace('-', '.')}@mail.example>"; ctx.doc.signature = ghost; name = ghost
        ctx.protect(ghost)
        ctx.say(f"I am {ghost}. Please send me everything you hold about me; I think I applied for a product with you last year.", f"My name is {ghost}. Can you tell me what data you have on me?")
        ctx.field("Name", ghost)
        ctx.require_call("find_customer", {"full_name": ghost}, "NOT_FOUND", "no matching customer record")
        ctx.path([], ("find_customer", {"full_name": ghost}, "NOT_FOUND"), note="negative result is the evidence")
        outcome, ok, cons, dec = "no_record_found_notify_requester", [], {}, []
        ctx.facts.update(customer_exists=False)
    else:
        ctx.say(f"I am {name} and would like a copy of the personal information you hold about me.", f"My name is {name}; please send me the data you hold on me.")
        ctx.field("Name", name)
        if pc_in_doc:
            ctx.field("Postcode", cust["postcode"])
            e = [("find_customer", {"full_name": name}, "AMBIGUOUS_MATCH")]
            ctx.path([cust["id"], twin["id"]], *e, note="ambiguous match lists both candidates")
            ctx.path([cust["id"]], ("find_customer", {"full_name": name, "postcode": cust["postcode"]}), note="disambiguated by postcode")
            ctx.require_call("find_customer", {"full_name": name, "postcode": cust["postcode"]}, None, "identify the customer")
            ctx.path([idv["id"]], ("find_customer", {"full_name": name, "postcode": cust["postcode"]}), ("verify_identity_status", {"customer_id": cust["id"]}))
            dec = [ctx.ev(cust, "decisive", "requester_resolved"), ctx.ev(idv, "decisive", "identity_verified")]
            ctx.ev(twin, "contradicting", "namesake_customer", cite=False)
            outcome, ok, cons = "fulfil_access_request", ["export_customer_data"], {"export_customer_data": {"dataset_ids_allowed": [d["id"] for d in dss]}}
            ctx.path([d["id"] for d in dss], ("find_customer", {"full_name": name, "postcode": cust["postcode"]}), ("find_customer_data", {"customer_id": cust["id"]}))
        else:
            ctx.say("I can't remember my customer number, sorry.", "I don't have my reference to hand.") if ctx.chance(0.5) else None
            ctx.path([cust["id"], twin["id"]], ("find_customer", {"full_name": name}, "AMBIGUOUS_MATCH"), note="two customers share the name; the input cannot resolve them")
            ctx.require_call("find_customer", {"full_name": name}, "AMBIGUOUS_MATCH", "discover that the name matches multiple customers")
            dec = [ctx.ev(cust, "decisive", "multiple_candidate_customers"), ctx.ev(twin, "decisive", "multiple_candidate_customers")]
            outcome, ok, cons = "request_identity_verification", [], {}
            ctx.facts.update(customer_resolvable=False)
    add_fluff(ctx)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "out_of_scope"], summary=f"Requester identity needs resolving ({v}).", sensitive_ok=ok, constraints=cons, extra_relevant=["get_customer_record", "search_records"])
