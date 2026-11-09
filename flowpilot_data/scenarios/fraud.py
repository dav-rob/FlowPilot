"""Supplier fraud detection families (invoice / bank-account change triggers)."""
from __future__ import annotations

from ..docs import Attachment
from ..util import ago, day
from ..world import mk_bank, mk_contact, mk_log, mk_supplier
from .base import Ctx, family
from .common import add_fluff, benign_history, mk_msg, namesake_supplier, sender_internal, staff
from .. import vocab

CAT = "supplier_fraud"


def _scaffold(ctx: Ctx, *, new_supplier: bool = False):
    """Supplier, ERP bank account, registered contact, PO + receipt, staff and benign history."""
    w, r = ctx.w, ctx.r
    ap, owner = staff(ctx, "Finance Operations")[0], staff(ctx, "Procurement")[0]
    sup = ctx.adopt(mk_supplier(w, r, owner_employee_id=owner["id"], onboarded_on=day(r.randrange(5, 25) if new_supplier else r.randrange(300, 2000))))
    old = ctx.adopt(mk_bank(w, r, sup, "active", since_days=r.randrange(5, 25) if new_supplier else r.randrange(400, 1800)))
    contact = ctx.adopt(mk_contact(w, r, sup))
    sup["trading_names"] = [f"{r.pick(vocab.TOWNS)} {sup['category']} Trading"] if ctx.chance(0.3) else []
    if not new_supplier:
        benign_history(ctx, sup, owner, ap)
    ctx.protect(sup["name"], sup["name"].split()[0])
    if ctx.conflicting:  # obsolete duplicate supplier master record with a near-identical name
        twin = namesake_supplier(ctx, sup)
        twin["status"] = "inactive"; twin["notes"] = "Duplicate vendor record retained for history; merge pending"
        ctx.facts["namesake"] = twin["id"]; ctx.mark_conflict()
    amount = r.choice([4_850.00, 12_400.50, 18_250.00, 36_900.00, 72_000.00, 7_315.40])
    po = ctx.add("purchase_orders", supplier_id=sup["id"], po_number=f"PO-{r.digits(6)}", description=f"{r.pick(vocab.GOODS)} - quarterly", status="approved",
                 total_gbp=amount, remaining_gbp=amount, approver_id=owner["id"], raised_on=day(r.randrange(30, 120)),
                 lines=[{"line": 1, "description": r.pick(vocab.GOODS), "amount_gbp": amount}])
    grn = ctx.add("goods_receipts", purchase_order_id=po["id"], description="Services received and signed off", received_on=day(r.randrange(2, 20)), amount_gbp=amount, received_by=ap["id"])
    return ap, owner, sup, old, contact, po, grn, amount


def _invoice(ctx: Ctx, sup, po, amount, bank_fields, msg=None, number=None, **over):
    r = ctx.r
    num = number or f"{r.pick(['SI', 'IN', 'HL'])}-{r.digits(5)}"
    inv = ctx.add("invoices", supplier_id=sup["id"], invoice_number=num, purchase_order_id=po["id"] if po else None, po_reference=po["po_number"] if po else None,
                  description=po["description"] if po else "services", total_gbp=amount, currency="GBP", status="awaiting_payment", received_on=day(r.randrange(0, 3)),
                  remit_to=bank_fields, source_message_id=msg["id"] if msg else None, **over)
    ctx.add("payments", invoice_id=inv["id"], supplier_id=sup["id"], payment_reference=f"RUN-{r.digits(6)}", status="scheduled", scheduled_for=day(-r.randrange(2, 6)), amount_gbp=amount)
    return inv


def _invoice_attachment(ctx: Ctx, sup, inv, po, bank, amount, extra=None):
    lines = [("Supplier", sup["name"]), ("VAT registration", sup["vat_number"]), ("Invoice number", inv["invoice_number"]),
             ("Purchase order", po["po_number"] if po else "n/a"), ("Invoice date", ctx.dt(inv["received_on"])), ("Total payable", f"£{amount:,.2f}"),
             ("Pay to account name", bank["account_name"]), ("Sort code", bank["sort_code"]), ("Account number", bank["account_number"])] + (extra or [])
    ctx.attach(Attachment("Invoice", lines, kind=ctx.pick(["scan", "scan", "md"])))


def _entries(ctx: Ctx, sup, inv):
    """Valid ways to reach the supplier id starting from document-visible facts."""
    out = [[("search_invoices", {"invoice_number": inv["invoice_number"]})]] if inv else [[]]
    toks = sup["name"].lower().replace(".", " ").split()
    if sum(1 for s in ctx.w.tables["suppliers"] if any(all(t in n.lower() for t in toks) for n in [s["name"]] + s.get("trading_names", []))) == 1:
        out.append([("find_supplier", {"name": sup["name"]})])
    out.append([("find_supplier", {"vat_number": sup["vat_number"]})])
    return out


def _msg_paths(ctx: Ctx, inv, msg, ids):
    """Two ways to reach the gateway record: via the invoice's source message, or via the message id printed in the input."""
    ctx.path(ids, ("search_invoices", {"invoice_number": inv["invoice_number"]}), ("verify_email_origin", {"message_id": msg["id"]}), note="message id taken from the invoice record")
    if ctx.doc.message_id:
        ctx.path(ids, ("verify_email_origin", {"message_id": msg["rfc_message_id"]}), note="message id taken from the email header/reference")


def _paths(ctx: Ctx, sup, inv, msg, finds: dict):
    for entry in _entries(ctx, sup, inv):
        for tool, ids in finds.items():
            if tool != "verify_email_origin" and ids:
                ctx.path(ids, *entry, (tool, {"supplier_id": sup["id"]}))
    if msg and "verify_email_origin" in finds:
        _msg_paths(ctx, inv, msg, finds["verify_email_origin"])


def _sender_for(ctx, sup, contact):
    return f"{contact['name']} <{contact['email']}>"


@family("fraud_invoice_bank_details", CAT, ["legit_change", "spoofed_lookalike", "change_unverified"])
def fraud_invoice_bank_details(ctx: Ctx):
    """Invoice arrives showing bank details that differ from the one the requester assumes is current."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    ap, owner, sup, old, contact, po, grn, amount = _scaffold(ctx)
    new = ctx.add("supplier_bank_accounts", supplier_id=sup["id"], account_name=sup["name"], sort_code=w.sort_code(r), account_number=w.account_number(r), status="pending", bank_name="Fictional Bank plc (synthetic)", added_on=day(r.randrange(3, 14)))
    new["iban"] = w.iban(new["sort_code"], new["account_number"])
    ev_decisive = []
    if v == "legit_change":
        new["status"] = "active"; old["status"] = "superseded"; sup["active_bank_account_id"] = new["id"]
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change via supplier portal; dual authorised; call-back verified", change_type="bank_details", status="applied",
                      requested_at=ago(r.randrange(9, 14), rng=r), requested_by_email=contact["email"], channel="supplier_portal", authorised_by=[owner["id"], ap["id"]], verification="callback_verified", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(8, 13), rng=r), called_number=contact["phone"], outcome="verified", notes="Confirmed change with registered contact on verified number", performed_by=ap["id"], change_id=scr["id"])
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim=("none" if ctx.conflicting else "pass"), dmarc="pass" if not ctx.conflicting else "none", first_seen=False, claimed_domain=sup["email_domain"], subject="Invoice")
        for rec in (scr, cbk, new): ev_decisive.append(ctx.ev(rec, "decisive", "change_authorised_and_verified"))
        ctx.ev(msg, "supporting", "sender_authentic")
        ctx.facts.update(bank_change_legitimate=True)
        outcome, sens = "approve_and_process", None
    elif v == "spoofed_lookalike":
        fake = contact["email"].replace("@" + sup["email_domain"], "@" + sup["email_domain"].replace(".example", "-accounts.example") if not ctx.conflicting else "@" + sup["email_domain"])
        msg = mk_msg(ctx, fake, spf=("fail" if not ctx.conflicting else "pass"), dkim=("fail" if not ctx.conflicting else "pass"), dmarc=("fail" if not ctx.conflicting else "pass"),
                     reply_to=f"payments@{sup['email_domain'].replace('.example', '-pay.example')}", lookalike=not ctx.conflicting, first_seen=True, geo="GB" if ctx.conflicting else "XX", claimed_domain=sup["email_domain"], subject="Invoice")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Contact phone number change requested by email; not verified", change_type="contact", status="rejected", requested_at=ago(r.randrange(1, 4), rng=r),
                      requested_by_email=msg["sender"], channel="email", authorised_by=[], verification="not_performed") if ctx.conflicting else None
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(300, 700), rng=r), called_number=contact["phone"], outcome="verified", notes="Annual verification of remittance details", performed_by=ap["id"], change_id=None)
        ev_decisive += [ctx.ev(msg, "decisive", "email_not_authentic"), ctx.ev(old, "decisive", "erp_account_differs_from_invoice")]
        if scr: ev_decisive.append(ctx.ev(scr, "decisive", "no_authorised_change_request"))
        ctx.ev(cbk, "supporting", "no_recent_callback")
        ctx.facts.update(bank_change_legitimate=False, invoice_account_in_erp=False)
        outcome, sens = "hold_payment_and_open_fraud_case", None
    else:
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change requested by email; awaiting call-back verification", change_type="bank_details", status="pending_verification",
                      requested_at=ago(r.randrange(1, 4), rng=r), requested_by_email=contact["email"], channel="email", authorised_by=[ap["id"]], verification="callback_pending", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(0, 2), rng=r), called_number=contact["phone"], outcome="no_answer", notes="Voicemail left on registered number; retry required", performed_by=ap["id"], change_id=scr["id"])
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", first_seen=False, claimed_domain=sup["email_domain"], subject="Invoice")
        for rec in (scr, cbk): ev_decisive.append(ctx.ev(rec, "decisive", "change_pending_unverified"))
        ctx.ev(old, "supporting", "erp_account_differs_from_invoice"); ctx.ev(msg, "supporting", "sender_authentic")
        ctx.facts.update(bank_change_legitimate=None, callback_outstanding=True)
        outcome, sens = "callback_verification_required", None
    inv = _invoice(ctx, sup, po, amount, {"account_name": new["account_name"], "sort_code": new["sort_code"], "account_number": new["account_number"]}, msg)
    ctx.facts.update(invoice_amount_gbp=amount, po_matches=True)
    ctx.ev(po, "context", "po_valid", cite=False); ctx.ev(grn, "context", "goods_received", cite=False)
    # document
    sender_ok = v != "spoofed_lookalike"
    ctx.doc.sender = f"{contact['name']} <{msg['sender']}>"; ctx.doc.message_id = msg["rfc_message_id"] if ctx.chance(0.8) else None
    ctx.doc.to = f"accounts.payable@{vocab.COMPANY['domain']}"
    ctx.doc.signature = f"{contact['name']}\nAccounts Receivable, {sup['name']}\n{contact['phone']}"
    ctx.doc.subject = ctx.pick([f"Invoice {inv['invoice_number']}", f"Payment of invoice {inv['invoice_number']}", f"{sup['name']} - invoice attached"])
    if ctx.vague:
        ctx.say("Please find attached our invoice for the work completed last month. Remittance details are on the attachment.", "Attached is our latest invoice. Could you let us know when it will be paid?")
    else:
        ctx.say(f"Please find attached invoice {inv['invoice_number']} for {vocab.GOODS[0] if False else po['description']} against {po['po_number']}.",
                f"Attached is our invoice {inv['invoice_number']} (PO {po['po_number']}) for £{amount:,.2f}.")
        ctx.say("Please note our bank details have changed - the new account is shown on the invoice and replaces the previous one.", "We have recently moved banks so payment should go to the account on the invoice rather than the old one.",
                "Please pay to the account shown on the invoice.")
    ctx.field("Invoice number", inv["invoice_number"]); ctx.field("Amount", f"£{amount:,.2f}")
    ctx.maybe_field("Supplier ID", sup["id"], corrupt_ok=True)
    _invoice_attachment(ctx, sup, inv, po, new, amount)
    add_fluff(ctx)
    ctx.protect(inv["invoice_number"])
    ctx.facts["path_entry_note"] = "supplier id is not stated in the input unless Supplier ID field is present"
    finds = {"get_supplier_change_history": [e for e in ev_decisive if ctx.w.table_of(e) in ("supplier_changes", "supplier_bank_accounts")] or [old["id"]],
             "get_callback_log": [cbk["id"]], "verify_email_origin": [msg["id"]], "get_supplier_record": [sup["active_bank_account_id"]]}
    _paths(ctx, sup, inv, msg, finds)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "out_of_scope"], summary=f"Invoice presents bank details differing from ERP history ({v}).", sensitive_ok=sens,
               review_case_type="fraud" if outcome.startswith(("hold", "reject")) else None, extra_relevant=["find_account_usage", "get_fraud_cases", "get_payment_status"])


@family("fraud_bank_change_request", CAT, ["legit_portal", "mailbox_compromise", "mule_account_reuse", "already_applied"])
def fraud_bank_change_request(ctx: Ctx):
    """Supplier asks to change bank details (no invoice)."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    ap, owner, sup, old, contact, po, grn, amount = _scaffold(ctx)
    other = ctx.adopt(mk_contact(w, r, sup, authorised=False, role="Sales Executive"))
    new = ctx.add("supplier_bank_accounts", supplier_id=sup["id"], account_name=sup["name"], sort_code=w.sort_code(r), account_number=w.account_number(r), status="pending", bank_name="Fictional Bank plc (synthetic)", added_on=day(1))
    new["iban"] = w.iban(new["sort_code"], new["account_number"])
    dec = []
    sender_contact = contact
    if v == "legit_portal":
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=sup["email_domain"], subject="Bank details update")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change submitted via authenticated supplier portal (MFA)", change_type="bank_details", status="pending_review", requested_at=ago(1, rng=r), requested_by_email=contact["email"],
                      channel="supplier_portal", authorised_by=[], verification="portal_mfa", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(0, hours=5, rng=r), called_number=contact["phone"], outcome="verified", notes="Registered contact confirmed new account details on verified number", performed_by=ap["id"], change_id=scr["id"])
        dec += [ctx.ev(scr, "decisive", "change_request_authenticated"), ctx.ev(cbk, "decisive", "callback_verified"), ctx.ev(new, "decisive", "pending_account")]
        outcome, sens = "approve_bank_change", ["update_supplier_bank_details"]
    elif v == "mailbox_compromise":
        sender_contact = other
        msg = mk_msg(ctx, other["email"], spf="pass", dkim="pass", dmarc="pass", first_seen=ctx.chance(0.5), geo="XX", claimed_domain=sup["email_domain"], subject="Bank details update")
        chg = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Contact phone number changed on request from unregistered mailbox", change_type="contact", status="applied", requested_at=ago(2, rng=r), requested_by_email=other["email"], channel="email", authorised_by=[], verification="not_performed")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change requested by email", change_type="bank_details", status="pending_verification", requested_at=ago(1, rng=r), requested_by_email=other["email"], channel="email", authorised_by=[], verification="callback_pending", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(200, 500), rng=r), called_number=contact["phone"], outcome="verified", notes="Annual verification", performed_by=ap["id"], change_id=None)
        dec += [ctx.ev(chg, "decisive", "recent_contact_change_unverified"), ctx.ev(other, "decisive", "requester_not_authorised"), ctx.ev(msg, "decisive", "unusual_origin")]
        outcome, sens = "reject_change_and_open_fraud_case", []
    elif v == "mule_account_reuse":
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=sup["email_domain"], subject="Bank details update")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change requested by email", change_type="bank_details", status="pending_verification", requested_at=ago(1, rng=r), requested_by_email=contact["email"], channel="email", authorised_by=[], verification="callback_pending", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(0, hours=3, rng=r), called_number=contact["phone"], outcome="verified", notes="Contact confirmed request on registered number", performed_by=ap["id"], change_id=scr["id"])
        victim = ctx.adopt(mk_supplier(w, r))
        frd = ctx.add("fraud_cases", supplier_id=victim["id"], summary="Payment diverted to mule account following mailbox compromise; account confirmed as mule", status="closed", outcome="confirmed_fraud", opened_on=day(r.randrange(60, 200)), beneficiary_account_number=new["account_number"])
        dec += [ctx.ev(frd, "decisive", "account_linked_to_prior_fraud")]; ctx.ev(cbk, "contradicting", "callback_verified_but_account_tainted")
        outcome, sens = "reject_change_and_open_fraud_case", []
    else:
        old["status"] = "superseded"; new["status"] = "active"; new["added_on"] = day(r.randrange(60, 120)); sup["active_bank_account_id"] = new["id"]
        msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=sup["email_domain"], subject="Bank details update")
        scr = ctx.add("supplier_changes", supplier_id=sup["id"], summary="Bank account change via portal; dual authorised; call-back verified; applied", change_type="bank_details", status="applied", requested_at=ago(r.randrange(60, 120), rng=r), requested_by_email=contact["email"], channel="supplier_portal", authorised_by=[owner["id"], ap["id"]], verification="callback_verified", new_bank_account_id=new["id"])
        cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(60, 120), rng=r), called_number=contact["phone"], outcome="verified", notes="Verified at time of original change", performed_by=ap["id"], change_id=scr["id"])
        dec += [ctx.ev(scr, "decisive", "already_applied"), ctx.ev(new, "decisive", "account_already_active")]
        outcome, sens = "no_action_already_applied", []
    ctx.facts.update(requester_registered=sender_contact is contact, new_account=new["account_number"])
    ctx.doc.sender = f"{sender_contact['name']} <{msg['sender']}>"; ctx.doc.message_id = msg["rfc_message_id"]; ctx.protect(msg["rfc_message_id"]); ctx.doc.to = f"supplier.support@{vocab.COMPANY['domain']}"
    ctx.doc.subject = ctx.pick(["Change of bank details", "Updated remittance information", f"{sup['name']} - account update"])
    ctx.doc.signature = f"{sender_contact['name']}\n{sender_contact['role']}, {sup['name']}"
    if ctx.vague:
        ctx.say("We're updating some of our records and would like our account information on your side to be brought up to date.", "Could you please make sure your records for us are current? Details below.")
    else:
        ctx.say("Please update our bank details with immediate effect. Future payments should be made to the account below.", "Following a change of bank we ask that you update our remittance account as per the details below.")
    ctx.field("Supplier", sup["name"]); ctx.field("Account name", new["account_name"]); ctx.field("Sort code", new["sort_code"]); ctx.field("Account number", new["account_number"])
    ctx.maybe_field("Supplier ID", sup["id"], corrupt_ok=True)
    if ctx.chance(0.5):
        ctx.attach(Attachment("Bank confirmation letter", [("Account holder", new["account_name"]), ("Sort code", new["sort_code"]), ("Account number", new["account_number"]), ("Letter date", ctx.dt(day(2)))], kind="scan"))
    add_fluff(ctx)
    ctx.protect(sup["name"])
    entry = [("find_supplier", {"vat_number": sup["vat_number"]})] if ctx.facts.get("namesake") else [("find_supplier", {"name": sup["name"]})]
    if ctx.chance(0.6) or ctx.facts.get("namesake"):
        ctx.field("VAT number", sup["vat_number"])
    vat_shown = any(a == "VAT number" for a, _ in ctx.doc.fields)
    entries = [e for e in _entries(ctx, sup, None)[1:] if e[0][1].get("name") or vat_shown]
    entries.append([("find_supplier", {"email_domain": msg["sender"].split("@")[-1]})]) if msg["sender"].split("@")[-1] == sup["email_domain"] else None
    finds = {"get_supplier_change_history": [e for e in dec if ctx.w.table_of(e) in ("supplier_changes", "supplier_bank_accounts")], "get_callback_log": [cbk["id"]],
             "get_supplier_record": [sup["active_bank_account_id"]] + [c["id"] for c in (contact, other)]}
    if v == "mule_account_reuse":
        ctx.path([frd["id"]], ("find_account_usage", {"account_number": new["account_number"]}), note="account reuse check from the account number in the input")
    if v == "mailbox_compromise":
        ctx.path([msg["id"]], ("verify_email_origin", {"message_id": msg["rfc_message_id"]}), note="message id from header")
    for e in entries:
        for tool, ids in finds.items():
            if tool != "verify_email_origin" and ids:
                if tool == "get_supplier_change_history" and not ids:
                    continue
                ctx.path(ids, *e, (tool, {"supplier_id": sup["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "contract_risk"], summary=f"Supplier requests a bank-detail change ({v}).", sensitive_ok=sens,
               review_case_type="fraud" if outcome.startswith("reject") else None, extra_relevant=["find_account_usage", "get_fraud_cases"])


@family("fraud_duplicate_or_mismatched_invoice", CAT, ["duplicate_resubmission", "credit_note_resubmission", "po_mismatch"])
def fraud_duplicate_or_mismatched_invoice(ctx: Ctx):
    """Chaser/duplicate invoice or amount not matching the purchase order."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    ap, owner, sup, old, contact, po, grn, amount = _scaffold(ctx)
    bank = {"account_name": old["account_name"], "sort_code": old["sort_code"], "account_number": old["account_number"]}
    num = f"{r.pick(['SI', 'IN', 'HL'])}-{r.digits(5)}"
    msg = mk_msg(ctx, contact["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=sup["email_domain"], subject="Invoice reminder")
    prior = _invoice(ctx, sup, po, amount, bank, None, number=num)
    dec = []
    if v == "duplicate_resubmission":
        prior["status"] = "paid"; prior["received_on"] = day(r.randrange(18, 40))
        pay = [p for p in ctx.w.tables["payments"] if p["invoice_id"] == prior["id"]][0]; pay.update(status="paid", paid_on=day(r.randrange(8, 17)))
        inv = _invoice(ctx, sup, po, amount, bank, msg, number=num.replace("-", " ") if ctx.chance(0.5) else num)
        po["remaining_gbp"] = 0
        dec += [ctx.ev(prior, "decisive", "same_invoice_already_paid"), ctx.ev(pay, "decisive", "payment_made")]
        outcome, sens = "reject_duplicate_invoice", []
    elif v == "credit_note_resubmission":
        prior["status"] = "cancelled"; prior["notes"] = "Cancelled - credit note issued for incorrect VAT; replacement invoice expected"
        pay = [p for p in ctx.w.tables["payments"] if p["invoice_id"] == prior["id"]][0]; pay.update(status="cancelled")
        inv = _invoice(ctx, sup, po, amount, bank, msg, number=num + "A")
        dec += [ctx.ev(prior, "decisive", "earlier_invoice_cancelled_credit_noted"), ctx.ev(pay, "decisive", "no_payment_made")]
        outcome, sens = "approve_and_process", ["release_payment"]
    else:
        prior["status"] = "superseded"
        inflated = round(amount * r.choice([1.18, 1.35, 1.6]), 2)
        grn["amount_gbp"] = round(amount * 0.6, 2); grn["description"] = "Partial delivery received (first tranche)"
        inv = _invoice(ctx, sup, po, inflated, bank, msg, number=num + "B")
        dec += [ctx.ev(po, "decisive", "invoice_exceeds_po"), ctx.ev(grn, "decisive", "partial_receipt")]
        ctx.facts.update(invoice_amount_gbp=inflated)
        outcome, sens = "query_supplier_discrepancy", []
    ctx.ev(prior, "context" if prior not in dec else "decisive", "earlier_invoice_history", cite=False)
    ctx.facts.update(invoice_number=inv["invoice_number"], po_amount=amount)
    ctx.doc.sender = f"{contact['name']} <{msg['sender']}>"; ctx.doc.message_id = msg["rfc_message_id"]; ctx.doc.to = f"accounts.payable@{vocab.COMPANY['domain']}"
    ctx.doc.signature = f"{contact['name']}\nCredit Control, {sup['name']}"
    ctx.doc.subject = ctx.pick([f"Overdue: {inv['invoice_number']}", f"Reminder - invoice {inv['invoice_number']}", f"Invoice {inv['invoice_number']} copy"])
    if ctx.vague:
        ctx.say("We have not yet received payment for the attached - please advise.", "Chasing the attached invoice; our records show it as unpaid.")
    else:
        ctx.say(f"Our records show invoice {inv['invoice_number']} for £{inv['total_gbp']:,.2f} is still outstanding against {po['po_number']}. Please arrange payment.", f"Second reminder: invoice {inv['invoice_number']} remains unpaid. Copy attached.")
    ctx.field("Invoice number", inv["invoice_number"]); ctx.field("Amount", f"£{inv['total_gbp']:,.2f}")
    _invoice_attachment(ctx, sup, inv, po, {"account_name": bank["account_name"], "sort_code": bank["sort_code"], "account_number": bank["account_number"]}, inv["total_gbp"])
    add_fluff(ctx); ctx.protect(inv["invoice_number"])
    same_number = v == "duplicate_resubmission"
    pays = [p["id"] for p in ctx.w.tables["payments"] if p["invoice_id"] == prior["id"]]
    for entry, ids in (([("search_invoices", {"invoice_number": inv["invoice_number"]})], [prior["id"], inv["id"]] if same_number else [inv["id"]]),
                       ([("search_invoices", {"po_number": po["po_number"]})], [prior["id"], inv["id"]])):
        ctx.path(ids, *entry)
        if prior["id"] in ids:
            ctx.path(pays, *entry, ("get_payment_status", {"invoice_id": prior["id"]}))
        ctx.path([po["id"]], *entry, ("get_purchase_order", {"po_id": po["id"]}))
        ctx.path([grn["id"]], *entry, ("get_goods_receipts", {"po_id": po["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "out_of_scope"], summary=f"Supplier chases or resubmits an invoice ({v}).", sensitive_ok=sens, extra_relevant=["get_invoice"])


@family("fraud_urgent_new_payee", CAT, ["no_po_urgent_fraud", "legit_urgent_new_supplier", "onboarding_incomplete"])
def fraud_urgent_new_payee(ctx: Ctx):
    """Internal urgency pressure to pay a recently created supplier."""
    w, r, v = ctx.w, ctx.r, ctx.variant
    ap, owner, sup, old, contact, po, grn, amount = _scaffold(ctx, new_supplier=True)
    exec_ = staff(ctx, "Finance Operations")[0]
    exec_["job_title"] = "Finance Director"
    dec = []
    if v == "no_po_urgent_fraud":
        ext = f"{exec_['name'].split()[0].lower()}.{exec_['name'].split()[-1].lower()}@{vocab.COMPANY['domain'].replace('line', 'iine')}"
        msg = mk_msg(ctx, ext, spf="fail", dkim="none", dmarc="fail", lookalike=True, first_seen=True, geo="XX", claimed_domain=vocab.COMPANY["domain"], subject="Urgent payment")
        sup["onboarding_checks"] = "incomplete"; sup["notes"] = "Created under urgent onboarding exception; VAT and company checks outstanding"
        po["status"] = "not_raised"; po["total_gbp"] = 0; po["remaining_gbp"] = 0
        inv = _invoice(ctx, sup, None, amount, {"account_name": old["account_name"], "sort_code": old["sort_code"], "account_number": old["account_number"]}, msg)
        dec += [ctx.ev(msg, "decisive", "executive_impersonation"), ctx.ev(sup, "decisive", "onboarding_incomplete_new_supplier")]
        outcome, sens = "hold_payment_and_open_fraud_case", ["place_payment_hold"]
    elif v == "legit_urgent_new_supplier":
        msg = mk_msg(ctx, exec_["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=vocab.COMPANY["domain"], subject="Urgent payment")
        sup["onboarding_checks"] = "complete"
        inv = _invoice(ctx, sup, po, amount, {"account_name": old["account_name"], "sort_code": old["sort_code"], "account_number": old["account_number"]}, msg)
        ctx.add("supplier_changes", supplier_id=sup["id"], summary="New supplier onboarding completed; bank account verified by call-back", change_type="onboarding", status="applied", requested_at=ago(r.randrange(12, 22), rng=r), requested_by_email=None, channel="internal", authorised_by=[owner["id"], ap["id"]], verification="callback_verified")
        ob = ctx.w.tables["supplier_changes"][-1]; ctx.records.append(ob["id"])
        dec += [ctx.ev(sup, "decisive", "onboarding_complete"), ctx.ev(po, "decisive", "po_approved"), ctx.ev(ob, "decisive", "onboarding_callback_verified")]
        outcome, sens = "approve_and_process", ["release_payment"]
    else:
        msg = mk_msg(ctx, exec_["email"], spf="pass", dkim="pass", dmarc="pass", claimed_domain=vocab.COMPANY["domain"], subject="Urgent payment")
        sup["onboarding_checks"] = "incomplete"; sup["notes"] = "VAT number validation outstanding"
        inv = _invoice(ctx, sup, po, amount, {"account_name": old["account_name"], "sort_code": old["sort_code"], "account_number": old["account_number"]}, msg)
        ctx.add("supplier_changes", supplier_id=sup["id"], summary="New supplier onboarding: VAT validation outstanding; bank account verified", change_type="onboarding", status="applied", requested_at=ago(r.randrange(5, 12), rng=r), requested_by_email=None, channel="internal", authorised_by=[owner["id"]], verification="callback_verified")
        ob = ctx.w.tables["supplier_changes"][-1]; ctx.records.append(ob["id"])
        dec += [ctx.ev(sup, "decisive", "onboarding_incomplete_but_po_valid"), ctx.ev(po, "supporting", "po_approved"), ctx.ev(ob, "decisive", "vat_validation_outstanding")]
        outcome, sens = "query_supplier_discrepancy", []
    cbk = ctx.add("callback_log", supplier_id=sup["id"], performed_at=ago(r.randrange(5, 20), rng=r), called_number=contact["phone"], outcome="verified" if v != "no_po_urgent_fraud" else "not_performed", notes="Onboarding verification record", performed_by=ap["id"], change_id=None)
    ctx.facts.update(invoice_amount_gbp=amount, supplier_age_days=ctx.w.tables["suppliers"][-1].get("age"), has_po=v != "no_po_urgent_fraud", executive_requested=True)
    ctx.doc.sender = f"{exec_['name']} <{msg['sender']}>"; ctx.doc.message_id = msg["rfc_message_id"]; ctx.doc.to = f"accounts.payable@{vocab.COMPANY['domain']}"
    ctx.doc.signature = exec_["name"] + "\nFinance Director"
    ctx.doc.subject = ctx.pick(["Urgent - payment needed today", "Please pay today", "Quick favour: supplier payment"])
    if ctx.vague:
        ctx.say("Need this one sorted before close of business - it's blocking something. Invoice attached, details on the attachment.", "Can you get the attached through today? I'm in meetings so can't take calls.")
    else:
        ctx.say(f"Please make a payment of £{amount:,.2f} to {sup['name']} today. Their invoice is attached; the supplier is new and has agreed to start immediately.", f"I need {sup['name']} paid today (£{amount:,.2f}) to avoid a service interruption. Invoice attached.")
    ctx.say("I'm travelling so can't take calls - please just process it.", "Keep this between us for now.") if v == "no_po_urgent_fraud" and not ctx.vague else ctx.say("PO and approvals are on file.", "Procurement has the paperwork.") if ctx.chance(0.5) else None
    ctx.field("Invoice number", inv["invoice_number"])
    _invoice_attachment(ctx, sup, inv, po if v != "no_po_urgent_fraud" else None, old, amount)
    add_fluff(ctx); ctx.protect(inv["invoice_number"], sup["name"])
    for entry in _entries(ctx, sup, inv):
        ctx.path([sup["id"]], *entry, ("get_supplier_record", {"supplier_id": sup["id"]}))
        ctx.path([e for e in dec if ctx.w.table_of(e) in ("supplier_changes",)] or [sup["id"]], *entry, ("get_supplier_change_history", {"supplier_id": sup["id"]}))
    _msg_paths(ctx, inv, msg, [msg["id"]])
    if v != "no_po_urgent_fraud":
        ctx.path([po["id"]], ("search_invoices", {"invoice_number": inv["invoice_number"]}), ("get_purchase_order", {"po_id": po["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "out_of_scope"], summary=f"Urgent payment instruction to a recent supplier ({v}).", sensitive_ok=sens, review_case_type="fraud" if outcome.startswith("hold") else None, extra_relevant=["get_payment_status", "get_fraud_cases"])
