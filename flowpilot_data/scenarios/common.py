"""Shared builder helpers across scenario families."""
from __future__ import annotations

from ..docs import fluff
from ..util import ago, day
from ..world import mk_bank, mk_contact, mk_employee, mk_log, mk_supplier, slug
from .. import vocab
from .base import Ctx


def staff(ctx: Ctx, dept: str, n: int = 1, **over):
    return [ctx.adopt(mk_employee(ctx.w, ctx.r, dept, **over)) for _ in range(n)]


def sender_internal(ctx: Ctx, emp: dict) -> None:
    ctx.doc.sender = f"{emp['name']} <{emp['email']}>"
    ctx.doc.signature = f"{emp['name']}\n{emp['job_title']}, {emp['department']}\n{vocab.COMPANY['name']}"


def add_fluff(ctx: Ctx) -> None:
    n = [0, 1, 2][ctx.d] if ctx.chance(0.7) else 0
    ctx.doc.paragraphs.extend(fluff(ctx.r, n))


def mk_msg(ctx: Ctx, sender: str, *, spf: str, dkim: str, dmarc: str, reply_to: str | None = None, lookalike: bool = False,
           first_seen: bool = False, geo: str = "GB", claimed_domain: str = "", subject: str = "", rfc_id: str | None = None) -> dict:
    r = ctx.r
    rfc = rfc_id or f"{r.hex(16).lower()}@{sender.split('@')[-1]}"
    dom = sender.split("@")[-1]
    return ctx.add(
        "email_messages", sender=sender, reply_to=reply_to or sender, subject=subject, rfc_message_id=rfc, received_at=ago(r.randrange(0, 2), rng=r),
        verdicts={"spf": spf, "dkim": dkim, "dmarc": dmarc},
        analysis={"sender_domain": dom, "claimed_org_domain": claimed_domain or dom, "lookalike_of_known_domain": lookalike,
                  "reply_to_differs_from_sender": bool(reply_to and reply_to != sender), "sender_first_seen_by_gateway": first_seen, "origin_geo": geo},
        raw_headers={"authentication_results": f"spf={spf}; dkim={dkim}; dmarc={dmarc}", "return_path": sender, "reply_to": reply_to or sender,
                     "received": [f"from mail.{dom} ({geo}) by gateway.{vocab.COMPANY['domain']}"], "x_originating_geo": geo})


def benign_history(ctx: Ctx, sup: dict, owner: dict, ap: dict) -> None:
    """Records every supplier has regardless of scenario outcome (prevents 'a record exists' becoming the signal)."""
    r = ctx.r
    ctx.add("supplier_changes", supplier_id=sup["id"], summary="Registered address updated", change_type="address", status="applied",
            requested_at=ago(r.randrange(300, 900), rng=r), requested_by_email=None, channel="supplier_portal", authorised_by=[owner["id"]], verification="not_required")
    if ctx.chance(0.5):
        ctx.add("supplier_changes", supplier_id=sup["id"], summary="Payment terms confirmed at annual review", change_type="terms", status="applied",
                requested_at=ago(r.randrange(100, 300), rng=r), requested_by_email=None, channel="internal", authorised_by=[ap["id"]], verification="not_required")
    mk_log(ctx.w, r, sup["id"], "Supplier record viewed during annual review", ap["id"], ago(r.randrange(20, 200), rng=r), "view")
    ctx.records.append(ctx.w.tables["audit_log"][-1]["id"])
    if ctx.chance(0.4):
        ctx.add("fraud_cases", supplier_id=sup["id"], summary="Phishing email impersonating supplier reported; no payment made; closed", status="closed", outcome="no_loss",
                opened_on=day(r.randrange(250, 700)), beneficiary_account_number=None)


def namesake_supplier(ctx: Ctx, sup: dict) -> dict:
    """A different legal entity with a near-identical name (used for ambiguity)."""
    r = ctx.r
    twin = ctx.adopt(mk_supplier(ctx.w, r, name=sup["name"].replace(" Ltd", " (UK) Ltd").replace(" Limited", " (UK) Limited") if "Ltd" in sup["name"] or "Limited" in sup["name"] else sup["name"] + " (UK)"))
    mk_bank(ctx.w, r, twin)
    ctx.records.append(ctx.w.tables["supplier_bank_accounts"][-1]["id"])
    return twin
