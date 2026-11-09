"""Regulatory compliance audit families (synthetic policy / notice fixtures; not real regulation)."""
from __future__ import annotations

from ..docs import Attachment
from ..util import ago, day, future_day
from ..world import mk_database, mk_system
from .base import Ctx, family
from .common import add_fluff, sender_internal, staff
from .. import vocab

CAT = "regulatory_compliance"
BODY = "Fictional Financial Standards Board (FFSB)"
NOTE = "SYNTHETIC FIXTURE - not a real regulatory instrument or legal guidance."


def _setup(ctx: Ctx, n_sys: int = 2, cls="customer_pii"):
    w, r = ctx.w, ctx.r
    comp = staff(ctx, "Compliance")[0]
    estate = f"{r.pick(vocab.TOWNS)} Estate {r.digits(2)}"
    ctx.protect(estate)
    owners = staff(ctx, "Technology Operations", n_sys)
    systems, dbs = [], []
    for o in owners:
        s = ctx.adopt(mk_system(w, r, owner_employee_id=o["id"], estate=estate, data_classification=cls, hosting="cloud", criticality="tier_1", lifecycle="live"))
        s["description"] += f" (estate {estate})"
        d = ctx.adopt(mk_database(w, r, s, facts=dict(collected_at=ago(r.randrange(0, 3), rng=r))))
        systems.append(s); dbs.append(d)
    if ctx.conflicting:  # decommissioned sibling system with deliberately non-compliant settings: a trap for agents that skip scope discovery
        o = staff(ctx, "Technology Operations")[0]
        dead = ctx.adopt(mk_system(w, r, owner_employee_id=o["id"], estate=estate, data_classification=cls, hosting="cloud", criticality="tier_1", lifecycle="decommissioned"))
        dead["description"] += f" (estate {estate})"
        ddb = ctx.adopt(mk_database(w, r, dead, facts=dict(encrypted_at_rest=False, log_retention_days=30, collected_at=ago(400, rng=r))))
        ctx.facts["decommissioned_sibling"] = dead["id"]; ctx.mark_conflict()
        ctx.ev(dead, "context", "decommissioned_out_of_scope", cite=False)
    return comp, estate, systems, dbs


def _notice(ctx: Ctx, comp, estate, title, summary, clauses, criteria_extra=None) -> dict:
    r = ctx.r
    ref = f"FFSB-SN-{2026}-{r.digits(3)}"
    crit = {"estates": [estate], "data_classification": ["customer_pii", "confidential"], **(criteria_extra or {})}
    pol = ctx.add("policies", title=title, reference=ref, kind="regulatory_notice", issuer=BODY, effective_date=future_day(r.randrange(10, 60)), status="published",
                  summary=summary + " " + NOTE, clauses=clauses, applicability=crit, version="1.0", note=NOTE)
    ctx.protect(ref)
    return pol


def _ctl(ctx: Ctx, system, cat_title, status="implemented", tested=None, ref="CTL"):
    r = ctx.r
    cat = ctx.add("control_catalogue", title=cat_title, reference=f"FPC-{r.digits(3)}", objective=f"Synthetic control objective: {cat_title}", test_procedure="Synthetic test procedure")
    c = ctx.add("controls", system_id=system["id"], control_catalogue_id=cat["id"], control_ref=cat["reference"], status=status, last_tested=day(tested if tested is not None else r.randrange(20, 120)), evidence_ref=f"EVI-{r.digits(5)}")
    return c


def _doc(ctx: Ctx, comp, pol, estate, subject_alts, asks, vague):
    sender_internal(ctx, comp)
    ctx.doc.subject = ctx.pick(subject_alts)
    if ctx.vague:
        ctx.say(*vague)
        ctx.field("Notice reference", pol["reference"])
    else:
        ctx.say(f"{BODY} has published notice {pol['reference']} ({pol['title']}). It takes effect on {ctx.dt(pol['effective_date'])}.", f"New notice {pol['reference']} - '{pol['title']}' - has been issued by {BODY}.")
        ctx.say(*asks)
        ctx.field("Notice reference", pol["reference"]); ctx.field("Estate in scope", estate)
    ctx.maybe_field("Policy record", pol["id"], corrupt_ok=True)
    ctx.attach(Attachment("Notice summary", [("Reference", pol["reference"]), ("Issuer", BODY), ("Title", pol["title"]), ("Status", "published (synthetic fixture)")], body=pol["summary"], kind=ctx.pick(["md", "scan"])))
    add_fluff(ctx)
    ctx.doc.to = f"compliance.mailbox@{vocab.COMPANY['domain']}"


def _paths(ctx: Ctx, pol, estate, systems, per_system, policy_finds=None):
    ref = pol["reference"]
    entry = [("search_records", {"query": ref, "record_types": ["policy"]})]
    ctx.path([pol["id"]], *entry, ("get_policy", {"policy_id": pol["id"]}))
    scoped = [s["id"] for s in systems] + ([ctx.facts["decommissioned_sibling"]] if ctx.facts.get("decommissioned_sibling") else [])
    ctx.path(scoped, *entry, ("discover_affected_systems", {"policy_id": pol["id"]}))
    if any(a == "Policy record" for a, _ in ctx.doc.fields) and not ctx.id_corrupted:
        ctx.path(scoped, ("discover_affected_systems", {"policy_id": pol["id"]}))
    for s in systems:
        for tool, argname, ids, extra in per_system(s):
            base_steps = [("discover_affected_systems", {"policy_id": pol["id"]})]
            pres = [entry + base_steps]
            if any(a == "Estate in scope" for a, _ in ctx.doc.fields):
                pres.append([("search_records", {"query": estate, "record_types": ["system"], "limit": 20})])
            for pre in pres:
                steps = list(pre)
                if argname == "database_id":
                    steps.append(("list_system_databases", {"system_id": s["id"]}))
                    d = next(d for d in ctx.w.tables["databases"] if d["system_id"] == s["id"])
                    steps.append((tool, {"database_id": d["id"], **extra}))
                else:
                    steps.append((tool, {argname: s["id"], **extra}))
                ctx.path(ids, *steps)


@family("compliance_encryption_notice", CAT, ["all_compliant", "gap_unencrypted_database", "exception_in_place"])
def compliance_encryption_notice(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    comp, estate, systems, dbs = _setup(ctx, 2)
    pol = _notice(ctx, comp, estate, "Encryption of customer data at rest", "Customer-data databases must be encrypted at rest with keys rotated within 365 days.",
                  [{"clause": "3.1", "text": "Databases holding customer personal data must be encrypted at rest."}, {"clause": "3.2", "text": "Encryption keys must be rotated at least every 365 days."}])
    gap_i = r.randrange(len(systems))
    for i, (s, d) in enumerate(zip(systems, dbs)):
        _ctl(ctx, s, "Encryption at rest", "implemented", tested=r.randrange(200, 420) if i == gap_i else r.randrange(30, 150))
        _ctl(ctx, s, "Key management", "implemented")
        ctx.add("audit_findings", system_id=s["id"], title="Prior audit: backup restoration test", summary="Closed finding from last year's audit", status="closed", raised_on=day(r.randrange(250, 600)))
        ctx.ev(s, "context", "system_in_scope", cite=False)
    dec = []
    if v == "all_compliant":
        for d in dbs: dec.append(ctx.ev(d, "decisive", "encrypted_and_key_age_ok"))
        outcome = "no_action_required"
    else:
        d = dbs[gap_i]; d["facts"].update(encrypted_at_rest=False, encryption_key_age_days=r.randrange(400, 700))
        dec.append(ctx.ev(d, "decisive", "database_not_encrypted"))
        for j, o in enumerate(dbs):
            if j != gap_i: ctx.ev(o, "supporting", "encrypted")
        if v == "gap_unencrypted_database":
            outcome = "open_audit_item_gap_found"
        else:
            exc = ctx.add("control_exceptions", system_id=systems[gap_i]["id"], title="Temporary encryption exception during migration", justification="Migration to new key service; compensating network isolation", approved_by=staff(ctx, "Information Security")[0]["id"], status="approved", valid_until=future_day(r.randrange(20, 90)), approved_on=day(r.randrange(10, 60)))
            dec.append(ctx.ev(exc, "decisive", "approved_exception_valid"))
            outcome = "monitor_approved_exception"
    ctx.facts.update(gap_system=systems[gap_i]["id"] if v != "all_compliant" else None)
    _doc(ctx, comp, pol, estate, ["New notice: encryption at rest", f"Notice {pol['reference']} - please assess", "Regulatory update for review"],
         ["Please identify which of our systems are affected and confirm whether encryption at rest is in place for each of them.", "Can Compliance work out which platforms are in scope and whether we meet the new encryption requirement?"],
         ["Something new has landed about how customer information is stored. Could the right people see whether any of our platforms are caught?", "The regulator's latest notice mentions data protection measures on stored records - not sure it affects us."])
    def per(s):
        out = [("run_database_query", "database_id", [d["id"] for d in dbs if d["system_id"] == s["id"]], {"query_name": "encryption_status"})]
        if v == "exception_in_place" and s["id"] == systems[gap_i]["id"]:
            out.append(("get_control_exceptions", "system_id", [exc["id"]], {}))
        return out
    _paths(ctx, pol, estate, systems, per)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "it_asset"], summary=f"New encryption notice; estate assessed ({v}).", review_case_type="audit" if outcome.startswith("open") else None,
               extra_relevant=["inspect_security_controls", "get_system", "get_audit_findings"])


@family("compliance_access_review_notice", CAT, ["reviews_current", "review_overdue", "evidence_missing"])
def compliance_access_review_notice(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    comp, estate, systems, dbs = _setup(ctx, 2)
    pol = _notice(ctx, comp, estate, "Quarterly review of privileged access", "Privileged access must be reviewed at least every 90 days and the review evidenced.",
                  [{"clause": "5.1", "text": "Privileged access reviews must be completed at least every 90 days."}, {"clause": "5.2", "text": "Review evidence must be retained by the system owner."}])
    bad_i = r.randrange(len(systems))
    dec = []
    for i, s in enumerate(systems):
        stale = v == "review_overdue" and i == bad_i
        missing = v == "evidence_missing" and i == bad_i
        for k in range(r.randrange(2, 4)):
            ctx.add("access_grants", system_id=s["id"], principal=f"adm-{r.hex(4).lower()}", role="administrator", privileged=True, mfa_enabled=True, account_type="human",
                    last_review=None if missing else day(r.randrange(100, 200) if stale else r.randrange(10, 80)), reviewer_id=None if missing else s["owner_employee_id"])
        grants = [g for g in w.tables["access_grants"] if g["system_id"] == s["id"]]
        ctl = _ctl(ctx, s, "Privileged access review", "not_tested" if missing else "implemented", tested=r.randrange(250, 400) if missing else r.randrange(15, 80))
        for g in grants:
            ctx.records.append(g["id"])
            if i == bad_i and v != "reviews_current": dec.append(ctx.ev(g, "decisive", "review_overdue" if stale else "review_evidence_missing"))
            elif v == "reviews_current": dec.append(ctx.ev(g, "decisive", "review_current"))
        if i == bad_i and v != "reviews_current":
            dec.append(ctx.ev(ctl, "decisive" if missing else "supporting", "review_control_status"))
        if missing:
            w.get(s["owner_employee_id"])["status"] = "on_leave"
            ctx.ev(w.get(s["owner_employee_id"]), "supporting", "owner_on_leave", cite=False)
        ctx.ev(s, "context", "system_in_scope", cite=False)
    outcome = {"reviews_current": "no_action_required", "review_overdue": "open_audit_item_gap_found", "evidence_missing": "request_owner_attestation"}[v]
    _doc(ctx, comp, pol, estate, ["Privileged access review - new requirement", f"{pol['reference']} access review frequency", "Update: access reviews"],
         ["Please confirm that privileged access reviews on the affected platforms meet the new 90-day requirement.", "Which of our systems are affected, and are their access reviews up to date?"],
         ["There's a new notice about how often certain admin permissions get looked at. Can someone tell me if we're fine?", "Sharing the latest update on periodic checks of elevated rights - do the platform owners know?"])
    def per(s):
        gids = [g["id"] for g in w.tables["access_grants"] if g["system_id"] == s["id"]]
        cids = [c["id"] for c in w.tables["controls"] if c["system_id"] == s["id"]]
        return [("get_access_grants", "system_id", gids, {"privileged_only": True}), ("inspect_security_controls", "system_id", cids, {})]
    _paths(ctx, pol, estate, systems, per)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "it_asset"], summary=f"Privileged-access review notice ({v}).", review_case_type="audit" if outcome.startswith("open") else None, extra_relevant=["get_system", "get_audit_findings"])


@family("compliance_log_retention_notice", CAT, ["retention_compliant", "one_system_short", "scope_exclusion"])
def compliance_log_retention_notice(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    comp, estate, systems, dbs = _setup(ctx, 3)
    pol = _notice(ctx, comp, estate, "Retention of audit logs", "Systems holding confidential or customer data must retain audit logs for at least 400 days.",
                  [{"clause": "7.1", "text": "Audit logs must be retained for 400 days minimum."}], {"hosting": ["cloud"]})
    i = r.randrange(len(systems))
    dec = []
    if v == "retention_compliant":
        for d in dbs: dec.append(ctx.ev(d, "decisive", "retention_ok")); d["facts"]["log_retention_days"] = r.choice([400, 450, 500])
        outcome = "no_action_required"
    elif v == "one_system_short":
        dbs[i]["facts"]["log_retention_days"] = r.choice([90, 180, 365])
        dec.append(ctx.ev(dbs[i], "decisive", "retention_short"))
        for j, d in enumerate(dbs):
            if j != i: d["facts"]["log_retention_days"] = 450; ctx.ev(d, "supporting", "retention_ok")
        outcome = "open_audit_item_gap_found"
    else:
        systems[i]["hosting"] = "on_premises"
        dbs[i]["facts"]["log_retention_days"] = r.choice([90, 180])
        for j, d in enumerate(dbs):
            if j != i: d["facts"]["log_retention_days"] = 450; dec.append(ctx.ev(d, "decisive", "retention_ok"))
        dec.append(ctx.ev(systems[i], "decisive", "system_outside_criteria"))
        outcome = "no_action_required"
    scoped = [s for k, s in enumerate(systems) if not (v == "scope_exclusion" and k == i)]
    _doc(ctx, comp, pol, estate, ["Audit log retention requirement", f"{pol['reference']}: log retention", "New notice on log retention"],
         ["We need to know which systems this applies to and whether their audit-log retention is sufficient.", "Please check log retention across the estate against the new requirement and tell us where we fall short."],
         ["Regulator wants records of activity kept for longer. I'd like a view on where that bites for us.", "New notice about how long system records must be held - can ops confirm we're covered?"])
    def per(s):
        d = next(d for d in dbs if d["system_id"] == s["id"])
        return [("run_database_query", "database_id", [d["id"]], {"query_name": "log_retention"})]
    ctx.facts["out_of_scope_system"] = systems[i]["id"] if v == "scope_exclusion" else None
    _paths(ctx, pol, estate, scoped, per)
    if v == "scope_exclusion":
        ctx.path([systems[i]["id"]], ("search_records", {"query": pol["reference"], "record_types": ["policy"]}), ("discover_affected_systems", {"policy_id": pol["id"]}))
    for s in systems: ctx.ev(s, "context", "system_in_estate", cite=False)
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "it_asset"], summary=f"Log-retention notice ({v}).", review_case_type="audit" if outcome.startswith("open") else None, extra_relevant=["get_system", "inspect_security_controls"])


@family("compliance_mfa_notice", CAT, ["privileged_gap", "service_accounts_exempt", "scope_unclear"])
def compliance_mfa_notice(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    comp, estate, systems, dbs = _setup(ctx, 2)
    pol = _notice(ctx, comp, estate, "Multi-factor authentication for privileged accounts", "Human privileged accounts must use multi-factor authentication; service accounts need documented compensating controls.",
                  [{"clause": "2.4", "text": "All privileged human accounts must enforce MFA."}, {"clause": "2.5", "text": "Service accounts without MFA need a compensating control exception."}])
    i = r.randrange(len(systems))
    dec = []
    for k, s in enumerate(systems):
        for _ in range(2):
            ctx.add("access_grants", system_id=s["id"], principal=f"adm-{r.hex(4).lower()}", role="administrator", privileged=True, mfa_enabled=True, account_type="human", last_review=day(r.randrange(10, 70)), reviewer_id=s["owner_employee_id"])
        ctx.ev(s, "context", "system_in_scope", cite=False)
    s = systems[i]
    if v == "privileged_gap":
        g = ctx.add("access_grants", system_id=s["id"], principal=f"adm-{r.hex(4).lower()}", role="database administrator", privileged=True, mfa_enabled=False, account_type="human", last_review=day(20), reviewer_id=s["owner_employee_id"])
        dec.append(ctx.ev(g, "decisive", "human_privileged_without_mfa")); outcome = "open_audit_item_gap_found"
    elif v == "service_accounts_exempt":
        exc = ctx.add("control_exceptions", system_id=s["id"], title="Service accounts: compensating controls (IP allow-list, vaulted secrets)", justification="Non-interactive batch accounts cannot enforce MFA", approved_by=staff(ctx, "Information Security")[0]["id"], status="approved", valid_until=future_day(r.randrange(100, 300)), approved_on=day(r.randrange(30, 200)))
        g = ctx.add("access_grants", system_id=s["id"], principal=f"svc-{r.hex(4).lower()}", role="batch operator", privileged=True, mfa_enabled=False, account_type="service", last_review=day(30), reviewer_id=s["owner_employee_id"], compensating_exception_id=exc["id"])
        dec += [ctx.ev(g, "decisive", "service_account_without_mfa"), ctx.ev(exc, "decisive", "compensating_control_documented")]; outcome = "no_action_required"
    else:
        s["data_classification"] = "unclassified"
        g = ctx.add("access_grants", system_id=s["id"], principal=f"adm-{r.hex(4).lower()}", role="administrator", privileged=True, mfa_enabled=False, account_type="human", last_review=day(25), reviewer_id=s["owner_employee_id"])
        dec += [ctx.ev(s, "decisive", "classification_missing_scope_unknown"), ctx.ev(g, "supporting", "possible_gap")]; outcome = "request_owner_attestation"
    _doc(ctx, comp, pol, estate, ["MFA for admin accounts - new notice", f"{pol['reference']} privileged MFA", "New MFA requirement - please check"],
         ["Please check whether privileged accounts on the in-scope systems are covered by MFA and raise audit items for any gaps.", "Do any admin accounts on our platforms lack MFA? Compliance needs an answer for the audit plan."],
         ["Another notice on how people sign in to sensitive systems. Could someone check we comply and let me know?", "Heads-up on a new sign-in security expectation for elevated users; please advise on our position."])
    def per(sx):
        gids = [g2["id"] for g2 in w.tables["access_grants"] if g2["system_id"] == sx["id"]]
        out = [("get_access_grants", "system_id", gids, {"privileged_only": True})]
        if v == "service_accounts_exempt" and sx["id"] == s["id"]:
            out.append(("get_control_exceptions", "system_id", [exc["id"]], {}))
        return out
    _paths(ctx, pol, estate, systems, per)
    if v == "scope_unclear":
        ctx.path([s["id"]], ("search_records", {"query": pol["reference"], "record_types": ["policy"]}), ("discover_affected_systems", {"policy_id": pol["id"]}), note="needs_classification_review lists the unclassified system")
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "it_asset"], summary=f"MFA notice ({v}).", review_case_type="audit" if outcome.startswith("open") else None, extra_relevant=["get_system", "inspect_security_controls"])
