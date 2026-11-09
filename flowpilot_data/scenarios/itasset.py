"""IT asset investigation families (CMDB / cloud inventory / ownership / deployment history / tickets)."""
from __future__ import annotations

from ..docs import Attachment
from ..util import ago, day
from ..world import mk_cmdb
from .base import Ctx, family
from .common import add_fluff, sender_internal, staff
from .. import vocab

CAT = "it_asset"


def _people(ctx: Ctx):
    secops = staff(ctx, "Information Security")[0]
    team = staff(ctx, "Cloud Platform", 2)
    mgr = staff(ctx, "Cloud Platform")[0]
    for t in team:
        t["manager_id"] = mgr["id"]
    return secops, team, mgr


def _cloud(ctx: Ctx, **over):
    r = ctx.r
    name = over.pop("resource_name", None) or f"vm-{r.hex(5).lower()}"
    ctx.protect(name)
    rec = dict(resource_name=name, resource_type="virtual_machine", public_ip=None, private_ip=f"10.{r.randrange(100, 199)}.{r.randrange(0, 250)}.{r.randrange(2, 250)}", status="running", region="uk-south",
               created_at=ago(r.randrange(5, 40), rng=r), created_by=None, tags={}, owner_id=None, last_seen=ago(0, rng=r))
    rec.update(over)
    return ctx.add("cloud_resources", **rec)


def _alert(ctx, asset, title, summary, proc, sev="high", status="open", days=1):
    return ctx.add("security_alerts", asset_id=asset["id"], title=title, summary=summary, process_name=proc, severity=sev, status=status, raised_at=ago(days, rng=ctx.r), source="endpoint_monitoring")


def _deploy(ctx, asset, actor, change_id, days, pipeline="ci-pipeline"):
    return ctx.add("deployments", asset_id=asset["id"], service_name=f"{pipeline}-{ctx.r.hex(3).lower()}", summary=f"Provisioned {asset.get('resource_name') or asset.get('hostname')} via {pipeline}", deployed_at=ago(days, rng=ctx.r), actor_id=actor["id"] if actor else None, pipeline=pipeline, change_id=change_id)


def _change(ctx, requester, approver, title, days, status="approved", scope=""):
    return ctx.add("changes", title=title, summary=f"{title}. {scope}".strip(), status=status, requester_id=requester["id"], approver_id=approver["id"], window_start=ago(days, rng=ctx.r), window_end=ago(days, hours=-4, rng=ctx.r), scope=scope or "standard")


def _stale_ticket(ctx: Ctx, asset, secops):
    """Conflict noise: an old, rejected ownership-transfer ticket that points at the wrong team."""
    if ctx.conflicting:
        t = ctx.add("tickets", title="Ownership transfer request", summary="Request to move ownership to another team - rejected, not applied", status="closed_rejected", opened_on=day(ctx.r.randrange(90, 400)),
                    requester_id=secops["id"], category="ownership", related_asset_id=asset["id"])
        ctx.mark_conflict(); ctx.ev(t, "contradicting", "stale_ownership_claim", cite=False)


def _doc(ctx: Ctx, analyst, subject_alts, text_alts, vague, fields, attach=None):
    sender_internal(ctx, analyst)
    ctx.doc.to = f"it.operations@{vocab.COMPANY['domain']}"
    ctx.doc.subject = ctx.pick(subject_alts)
    ctx.say(*(vague if ctx.vague else text_alts))
    for a, b in fields:
        ctx.field(a, b)
    if attach:
        ctx.attach(attach)
    add_fluff(ctx)


def _chain(ctx: Ctx, entries, asset_id, follow):
    """entries: list of entry step-lists leading to asset_id; follow: [(tool, args, finds)]"""
    for e in entries:
        ctx.path([asset_id], *e)
        for tool, args, finds in follow:
            ctx.path(finds, *e, (tool, args))


def _entries_cloud(ctx, res, shown_ip=True):
    out = [[("query_cloud_inventory", {"resource_name": res["resource_name"]})]]
    if shown_ip and res.get("public_ip") or (shown_ip and res.get("private_ip")):
        out.append([("query_cloud_inventory", {"ip_address": res.get("public_ip") or res["private_ip"]})])
    return out


@family("it_unrecognised_cloud_resource", CAT, ["authorised_untagged", "shadow_it_exposed", "abandoned_test_env"])
def it_unrecognised_cloud_resource(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    secops, team, mgr = _people(ctx)
    actor = team[0]
    ip_public = v == "shadow_it_exposed"
    res = _cloud(ctx, public_ip=f"198.51.100.{r.randrange(2, 250)}" if ip_public else None, created_by=actor["id"])
    dec = []
    if v == "authorised_untagged":
        chg = _change(ctx, actor, mgr, "Provision analytics worker VM", 14, scope="new VM in uk-south")
        dep = _deploy(ctx, res, actor, chg["id"], 14)
        res["tags"] = {"cost_centre": f"CC{r.digits(4)}"}
        dec = [ctx.ev(dep, "decisive", "deployed_through_pipeline"), ctx.ev(chg, "decisive", "approved_change"), ctx.ev(actor, "decisive", "creator_active_employee")]
        outcome, ok = "register_asset_and_assign_owner", []
    elif v == "shadow_it_exposed":
        actor["status"] = "left"; actor["end_date"] = day(r.randrange(10, 40))
        res["created_at"] = ago(r.randrange(1, 4), rng=r)
        al = _alert(ctx, res, "Inbound connections to unmanaged public IP", "Port scanning observed against unmanaged resource", "sshd", "high", days=0)
        dep = _deploy(ctx, res, None, None, 3, pipeline="manual-console")
        dec = [ctx.ev(al, "decisive", "exposed_and_suspicious"), ctx.ev(actor, "decisive", "creator_is_leaver"), ctx.ev(dep, "decisive", "no_change_record")]
        outcome, ok = "isolate_and_open_incident", ["isolate_asset"]
    else:
        actor["status"] = "left"; actor["end_date"] = day(r.randrange(80, 300))
        res["created_at"] = ago(r.randrange(200, 400), rng=r); res["last_seen"] = ago(0, rng=r)
        chg = _change(ctx, actor, mgr, "Temporary load-test environment", r.randrange(200, 380), status="closed", scope="3 month load test")
        dep = _deploy(ctx, res, actor, chg["id"], r.randrange(200, 380))
        res["tags"] = {"purpose": "load-test", "expires": day(r.randrange(100, 180))}
        dec = [ctx.ev(chg, "decisive", "change_closed_long_ago"), ctx.ev(actor, "decisive", "owner_left"), ctx.ev(dep, "supporting", "old_deployment")]
        outcome, ok = "decommission_stale_asset", ["decommission_asset"]
    _stale_ticket(ctx, res, secops)
    ctx.facts.update(resource=res["id"], public=ip_public)
    _doc(ctx, secops, ["Unrecognised VM in cloud estate", f"Asset discovered: {res['resource_name']}", "Cloud inventory exception"],
         [f"Our cloud posture scan found a VM called {res['resource_name']} that I can't match to a service. Can someone work out whose it is and what to do with it?", f"Resource {res['resource_name']} turned up in the weekly discovery with no owner tag."],
         ["Something in the cloud estate doesn't look right and has no clear owner - details below.", "Weekly discovery flagged a machine that nobody seems to claim."],
         [("Resource name", res["resource_name"]), ("Region", "uk-south"), ("Source", "weekly cloud discovery")] + ([("Public IP", res["public_ip"])] if res["public_ip"] else []))
    ctx.maybe_field("Asset ID", res["id"], corrupt_ok=True)
    entries = _entries_cloud(ctx, res, shown_ip=bool(res["public_ip"]))
    follow = [("lookup_asset_owner", {"asset_id": res["id"]}, [res["id"]]), ("get_deployment_history", {"asset_id": res["id"]}, [dep["id"]]),
              ("get_security_alerts", {"asset_id": res["id"]}, [d for d in dec if w.table_of(d) == "security_alerts"])]
    follow = [f for f in follow if f[2]]
    _chain(ctx, entries, res["id"], follow)
    for e in entries:
        if v != "shadow_it_exposed":
            ctx.path([chg["id"]], *e, ("get_deployment_history", {"asset_id": res["id"]}), ("get_change_record", {"change_id": chg["id"]}))
        ctx.path([actor["id"]], *e, ("get_deployment_history", {"asset_id": res["id"]}), ("get_employee", {"employee_id": actor["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"Unrecognised cloud resource ({v}).", sensitive_ok=ok, review_case_type="it_security" if outcome.startswith("isolate") else None,
               extra_relevant=["search_assets", "create_ticket"])


@family("it_inventory_discrepancy", CAT, ["stale_record_ip_reuse", "decommission_incomplete", "rogue_host_masquerading"])
def it_inventory_discrepancy(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    secops, team, mgr = _people(ctx)
    owner = team[0]
    host = f"hl{r.pick(['app', 'db', 'bat'])}{r.digits(3)}"
    ctx.protect(host)
    old = ctx.adopt(mk_cmdb(w, r, hostname=host, status="decommissioned", owner_id=owner["id"], asset_type="server", last_seen=ago(r.randrange(60, 200), rng=r), environment="prod", description="Retired batch server"))
    ip = old["ip_address"]
    dec = []
    if v == "stale_record_ip_reuse":
        new = ctx.adopt(mk_cmdb(w, r, hostname=f"hl{r.pick(['app', 'web'])}{r.digits(3)}", ip_address=ip, owner_id=team[1]["id"], status="in_service", asset_type="virtual_machine", last_seen=ago(0, rng=r), environment="prod"))
        chg = _change(ctx, team[1], mgr, f"Build {new['hostname']} and reuse address {ip}", r.randrange(10, 40), scope="reuse of released IP")
        dep = _deploy(ctx, new, team[1], chg["id"], r.randrange(10, 40))
        dec = [ctx.ev(new, "decisive", "ip_now_assigned_to_new_asset"), ctx.ev(chg, "decisive", "approved_ip_reuse"), ctx.ev(old, "decisive", "stale_decommissioned_record")]
        outcome, ok, obs = "reconcile_inventory_record", [], f"host responding on {ip}"
        ctx.path([old["id"], new["id"]], ("search_assets", {"ip_address": ip}, "AMBIGUOUS_MATCH"), note="ambiguous: two CMDB items share the address")
        ctx.require_call("search_assets", {"ip_address": ip}, "AMBIGUOUS_MATCH", "discover the address is claimed by two records")
        ctx.path([chg["id"]], ("search_assets", {"ip_address": ip}, "AMBIGUOUS_MATCH"), ("get_deployment_history", {"asset_id": new["id"]}), ("get_change_record", {"change_id": chg["id"]}))
    elif v == "decommission_incomplete":
        chg = _change(ctx, owner, mgr, f"Decommission {host}", r.randrange(30, 90), status="closed", scope="decommission; data wipe pending")
        old["last_seen"] = ago(0, rng=r); old["ip_address"] = ip
        ctx.add("tickets", title=f"Data wipe for {host}", summary="Disk wipe not yet confirmed by vendor", status="open", opened_on=day(r.randrange(30, 80)), requester_id=owner["id"], category="decommission", related_asset_id=old["id"])
        tk = ctx.w.tables["tickets"][-1]; ctx.records.append(tk["id"])
        dec = [ctx.ev(chg, "decisive", "decommission_change_incomplete"), ctx.ev(tk, "decisive", "wipe_not_confirmed"), ctx.ev(old, "decisive", "still_responding")]
        outcome, ok, obs = "complete_decommission_with_ticket", ["decommission_asset"], "decommissioned host still responding"
        ctx.path([old["id"]], ("search_assets", {"hostname": host}))
        ctx.path([tk["id"]], ("search_assets", {"hostname": host}), ("get_linked_records", {"record_id": old["id"]}))
        ctx.path([chg["id"]], ("search_records", {"query": host, "record_types": ["change"]}))
    else:
        old["mac_address"] = ":".join(r.hex(2) for _ in range(6))
        old["last_seen"] = ago(0, rng=r); old["status"] = "in_service"; old["ip_address"] = ip
        rogue_mac = ":".join(r.hex(2) for _ in range(6))
        al = ctx.add("security_alerts", asset_id=old["id"], title="Hardware address mismatch for known hostname", summary=f"Host answering as {host} presents MAC {rogue_mac}, CMDB records {old['mac_address']}", process_name="arp_monitor", severity="high", status="open", raised_at=ago(0, rng=r), source="network_monitoring")
        owner["status"] = "on_leave"
        dec = [ctx.ev(al, "decisive", "mac_mismatch_masquerade"), ctx.ev(old, "decisive", "registered_mac_differs")]
        outcome, ok, obs = "isolate_and_open_incident", ["isolate_asset"], f"hostname {host} seen with an unfamiliar hardware address"
        ctx.facts["observed_mac"] = rogue_mac
        ctx.path([al["id"]], ("search_assets", {"hostname": host}), ("get_security_alerts", {"asset_id": old["id"]}))
        ctx.path([old["id"]], ("search_assets", {"hostname": host}), ("get_cmdb_item", {"asset_id": old["id"]}))
    _stale_ticket(ctx, old, secops)
    ctx.facts.update(hostname=host, ip=ip)
    _doc(ctx, secops, ["Inventory discrepancy", f"Discovery mismatch for {host}", "CMDB vs network discovery"],
         [f"Network discovery reports {obs}, but the CMDB doesn't line up. Please investigate and fix the record or the host.", f"Reconciliation shows a mismatch involving {host} ({obs})."],
         ["Discovery and the CMDB disagree about one of our hosts. Can you take a look?", "Inventory reconciliation threw up an oddity - see the fields below."],
         [("Hostname", host), ("IP address", ip), ("Discovery source", "network scan")])
    ctx.facts["path_note"] = "CMDB id not given"
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"CMDB / discovery discrepancy ({v}).", sensitive_ok=ok, review_case_type="it_security" if outcome.startswith("isolate") else None,
               extra_relevant=["lookup_asset_owner", "get_employee", "create_ticket", "get_change_record"])


@family("it_security_anomaly", CAT, ["benign_patch_window", "unauthorised_process", "scanner_false_positive"])
def it_security_anomaly(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    secops, team, mgr = _people(ctx)
    owner = team[0]
    asset = ctx.adopt(mk_cmdb(w, r, owner_id=owner["id"], status="in_service", environment="prod", asset_type="server"))
    host = asset["hostname"]; ctx.protect(host)
    dec = []
    if v == "benign_patch_window":
        chg = _change(ctx, owner, mgr, "Monthly OS patching", 0, scope=f"patch window for {host}")
        al = _alert(ctx, asset, "Unexpected service restart and new binary", "Package manager updated system binaries", "patch-agent", "medium", days=0)
        dec = [ctx.ev(chg, "decisive", "patch_window_covers_activity"), ctx.ev(al, "supporting", "alert_matches_patching")]
        outcome, ok = "close_as_authorised_activity", []
    elif v == "unauthorised_process":
        al = _alert(ctx, asset, "Unknown binary running with outbound connections", "Unsigned binary spawned shell and connected to unfamiliar external host", f"bin_{r.hex(4).lower()}", "critical", days=0)
        other = _change(ctx, owner, mgr, "Quarterly certificate renewal", r.randrange(12, 30), status="closed", scope="different host group")
        owner["status"] = "on_leave"
        dec = [ctx.ev(al, "decisive", "unauthorised_process"), ctx.ev(owner, "supporting", "owner_unavailable")]
        outcome, ok = "isolate_and_open_incident", ["isolate_asset"]
        ctx.ev(other, "context", "unrelated_change", cite=False)
    else:
        scanner = ctx.adopt(mk_cmdb(w, r, owner_id=secops["id"], status="in_service", asset_type="server", description="Authorised vulnerability scanner", hostname=f"hlscan{r.digits(2)}"))
        tk = ctx.add("tickets", title="Scheduled authenticated vulnerability scan", summary=f"Approved scan from {scanner['ip_address']} against production estate including {host}", status="in_progress", opened_on=day(2), requester_id=secops["id"], category="security_scan", related_asset_id=scanner["id"])
        al = _alert(ctx, asset, "Port scan detected", f"Sequential port probing from {scanner['ip_address']}", "network_probe", "high", days=0)
        al["source_ip"] = scanner["ip_address"]
        dec = [ctx.ev(tk, "decisive", "approved_scan"), ctx.ev(scanner, "decisive", "source_is_known_scanner"), ctx.ev(al, "supporting", "alert_from_scanner")]
        outcome, ok = "close_as_authorised_activity", []
    _stale_ticket(ctx, asset, secops)
    ctx.facts.update(host=host, alert_title=al["title"])
    _doc(ctx, secops, ["Security alert on production host", f"Alert: {host}", "Anomaly needs triage"],
         [f"An alert fired on {host}: '{al['title']}'. Is this expected, or do we need to act?", f"EDR flagged {host} ({al['title']}). Please triage."],
         ["Something odd on one of the production servers. Can someone with context check whether it's expected?", "Monitoring raised an alert; the details are below."],
         [("Hostname", host), ("Alert", al["title"]), ("Severity", al["severity"])])
    ctx.maybe_field("Asset ID", asset["id"], corrupt_ok=True)
    entries = [[("search_assets", {"hostname": host})]]
    follow = [("get_security_alerts", {"asset_id": asset["id"]}, [al["id"]]), ("lookup_asset_owner", {"asset_id": asset["id"]}, [owner["id"]])]
    _chain(ctx, entries, asset["id"], follow)
    if v == "benign_patch_window":
        ctx.path([chg["id"]], ("search_records", {"query": host, "record_types": ["change"]}))
    if v == "scanner_false_positive":
        ctx.path([tk["id"]], ("search_assets", {"hostname": host}), ("get_security_alerts", {"asset_id": asset["id"]}), ("search_records", {"query": al["source_ip"], "record_types": ["ticket", "cmdb_item"]}))
        ctx.path([scanner["id"]], ("search_assets", {"hostname": host}), ("get_security_alerts", {"asset_id": asset["id"]}), ("search_assets", {"ip_address": al["source_ip"]}))
    if v == "unauthorised_process":
        ctx.path([owner["id"]], *entries[0], ("lookup_asset_owner", {"asset_id": asset["id"]}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "regulatory_compliance"], summary=f"Host security anomaly ({v}).", sensitive_ok=ok, review_case_type="it_security" if outcome.startswith("isolate") else None, extra_relevant=["get_change_record", "get_ticket", "get_employee"])


@family("it_endpoint_not_in_inventory", CAT, ["new_joiner_device", "leaver_unreturned_device", "duplicate_serial_typo"])
def it_endpoint_not_in_inventory(ctx: Ctx):
    w, r, v = ctx.w, ctx.r, ctx.variant
    secops, team, mgr = _people(ctx)
    emp = staff(ctx, "Customer Operations")[0]
    serial = f"SN{r.hex(8)}"
    host = f"hllap{r.digits(4)}"
    ctx.protect(host)
    dec = []
    if v == "new_joiner_device":
        emp["start_date"] = day(r.randrange(2, 8))
        tk = ctx.add("tickets", title=f"New joiner equipment for {emp['name']}", summary=f"Laptop {host} (serial {serial}) issued to new joiner {emp['name']}", status="closed", opened_on=day(r.randrange(5, 12)), requester_id=emp["manager_id"] or mgr["id"], category="joiner", related_employee_id=emp["id"])
        dev = ctx.add("cloud_resources", resource_name=host, resource_type="endpoint_mdm", public_ip=None, private_ip="10.220.4.9", status="enrolled", region="n/a", created_at=ago(r.randrange(1, 5), rng=r), created_by=None, tags={}, owner_id=None, last_seen=ago(0, rng=r), serial_number=serial)
        dec = [ctx.ev(tk, "decisive", "joiner_equipment_ticket"), ctx.ev(emp, "decisive", "active_new_joiner"), ctx.ev(dev, "supporting", "mdm_enrolment")]
        outcome, ok = "register_asset_and_assign_owner", []
        asset_id = dev["id"]
    elif v == "leaver_unreturned_device":
        emp["status"] = "left"; emp["end_date"] = day(r.randrange(14, 40))
        dev = ctx.adopt(mk_cmdb(w, r, hostname=host, serial_number=serial, owner_id=emp["id"], asset_type="laptop", status="in_service", last_seen=ago(0, rng=r), description="Corporate laptop", environment="prod"))
        tk = ctx.add("tickets", title=f"Leaver process for {emp['name']}", summary="Equipment return outstanding", status="open", opened_on=day(r.randrange(14, 40)), requester_id=emp["manager_id"] or mgr["id"], category="leaver", related_employee_id=emp["id"], related_asset_id=dev["id"])
        dec = [ctx.ev(emp, "decisive", "assigned_user_left"), ctx.ev(tk, "decisive", "return_outstanding"), ctx.ev(dev, "decisive", "still_active")]
        outcome, ok = "recover_device_and_open_ticket", []
        asset_id = dev["id"]
    else:
        dev = ctx.adopt(mk_cmdb(w, r, hostname=host, serial_number=serial, owner_id=emp["id"], asset_type="laptop", status="in_service", last_seen=ago(0, rng=r), description="Corporate laptop"))
        dup = ctx.adopt(mk_cmdb(w, r, hostname=host.replace("hllap", "hlold"), serial_number=serial, owner_id=None, asset_type="laptop", status="retired", last_seen=ago(r.randrange(200, 500), rng=r), description="Duplicate import row"))
        dec = [ctx.ev(dev, "decisive", "registered_with_matching_serial"), ctx.ev(dup, "decisive", "duplicate_import_record")]
        outcome, ok = "reconcile_inventory_record", []
        asset_id = dev["id"]
        ctx.path([dev["id"], dup["id"]], ("search_assets", {"serial_number": serial}, "AMBIGUOUS_MATCH"), note="serial is held by two records")
        ctx.require_call("search_assets", {"serial_number": serial}, "AMBIGUOUS_MATCH", "serial appears on two CMDB items")
    _stale_ticket(ctx, dev, secops)
    ctx.facts.update(hostname=host, serial=serial, employee=emp["id"])
    _doc(ctx, secops, ["Laptop not in asset inventory", f"Endpoint check-in: {host}", "Unregistered endpoint"],
         [f"Endpoint {host} (serial {serial}) is checking in but the inventory record looks wrong or missing. Please establish who has it and sort the record out.", f"The MDM console shows {host} active but we can't reconcile it to the CMDB."],
         ["There's a laptop checking in that nobody can place. Can you check the records?", "Inventory and MDM disagree about an endpoint."],
         [("Hostname", host), ("Serial", serial), ("Last check-in", ctx.dt(day(0)))])
    tkt = [d for d in dec if w.table_of(d) == "tickets"]
    if v == "new_joiner_device":
        e = [("query_cloud_inventory", {"resource_name": host})]
        ctx.path([asset_id], *e)
        ctx.path(tkt, ("search_records", {"query": host, "record_types": ["ticket"]}))
        ctx.path(tkt, ("search_records", {"query": serial, "record_types": ["ticket"]}))
        ctx.path([emp["id"]], ("search_records", {"query": host, "record_types": ["ticket"]}), ("get_ticket", {"ticket_id": tkt[0]}), ("get_employee", {"employee_id": emp["id"]}))
    elif v == "leaver_unreturned_device":
        e = [("search_assets", {"hostname": host})]
        ctx.path([asset_id], *e)
        ctx.path([emp["id"]], *e, ("lookup_asset_owner", {"asset_id": asset_id}))
        ctx.path(tkt, *e, ("get_linked_records", {"record_id": asset_id}))
        ctx.path([emp["id"]], *e, ("lookup_asset_owner", {"asset_id": asset_id}), ("get_employee", {"employee_id": emp["id"]}))
    else:
        ctx.path([asset_id], ("search_assets", {"hostname": host}))
    ctx.finish(primary=CAT, outcome=outcome, competing=[CAT, "supplier_fraud"], summary=f"Endpoint missing from inventory ({v}).", sensitive_ok=ok, review_case_type="it_security" if outcome.startswith("recover") else None, extra_relevant=["get_employee", "get_ticket", "create_ticket"])
