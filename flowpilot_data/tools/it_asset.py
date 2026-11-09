"""CMDB, cloud inventory, ownership directory, deployment history and ticketing tools."""
from __future__ import annotations

from .core import ToolError, tool


class ItTools:
    def _asset(self, asset_id: str) -> tuple[str, dict]:
        self._need(asset_id=asset_id)
        hit = self.env.get(asset_id.strip())
        if hit is None:
            raise ToolError("NOT_FOUND", f"No CMDB item or cloud resource {asset_id!r}")
        if hit[0] not in ("cmdb_items", "cloud_resources"):
            raise ToolError("WRONG_RECORD_TYPE", f"{asset_id} is not an asset record", record_type=hit[0])
        return hit[0], dict(hit[1])

    @tool
    def lookup_asset_owner(self, asset_id: str) -> dict:
        """Ownership directory lookup for a CMDB item or cloud resource: owner, status and manager."""
        t, a = self._asset(asset_id)
        oid = a.get("owner_id")
        if not oid:
            return {"asset_id": a["id"], "owner": None, "owner_status": "unassigned", "note": "no owner recorded; check tags and deployment history"}
        emp = self.env.get(oid)
        mgr = self.env.get(emp[1]["manager_id"]) if emp and emp[1].get("manager_id") else None
        return {"asset_id": a["id"], "owner": emp[1] if emp else None, "manager": mgr[1] if mgr else None}

    @tool
    def query_cloud_inventory(self, asset_id: str | None = None, ip_address: str | None = None, resource_name: str | None = None) -> dict:
        """Cloud inventory lookup by resource id, IP address or resource name."""
        if not any([asset_id, ip_address, resource_name]):
            raise ToolError("INVALID_ARGUMENT", "provide asset_id, ip_address or resource_name")
        hits = []
        for r in self.env.rows("cloud_resources"):
            if asset_id and r["id"] != asset_id:
                continue
            if ip_address and ip_address not in (r.get("public_ip"), r.get("private_ip")):
                continue
            if resource_name and resource_name.lower() not in r["resource_name"].lower():
                continue
            hits.append(r)
        if not hits:
            raise ToolError("NOT_FOUND", "No cloud resource matches")
        return {"resources": hits, "count": len(hits)}

    @tool
    def get_cmdb_item(self, asset_id: str) -> dict:
        """CMDB configuration item (hostname, serial, IP, status, owner id, last seen)."""
        return {"item": self._rec("cmdb_items", asset_id, "asset_id")}

    @tool
    def search_assets(self, hostname: str | None = None, ip_address: str | None = None, serial_number: str | None = None, mac_address: str | None = None) -> dict:
        """Search CMDB and cloud inventory by hostname, IP, serial number or MAC. Errors if none or several match."""
        if not any([hostname, ip_address, serial_number, mac_address]):
            raise ToolError("INVALID_ARGUMENT", "provide hostname, ip_address, serial_number or mac_address")
        hits = []
        for c in self.env.rows("cmdb_items"):
            if ((hostname and c["hostname"].lower() == hostname.lower()) or (ip_address and c["ip_address"] == ip_address)
                    or (serial_number and c["serial_number"].lower() == serial_number.lower()) or (mac_address and c["mac_address"].lower() == mac_address.lower())):
                hits.append(("cmdb_item", c))
        for r in self.env.rows("cloud_resources"):
            if (hostname and r["resource_name"].lower() == hostname.lower()) or (ip_address and ip_address in (r.get("public_ip"), r.get("private_ip"))):
                hits.append(("cloud_resource", r))
        if not hits:
            raise ToolError("NOT_FOUND", "No asset matches the identifiers")
        if len(hits) > 1:
            raise ToolError("AMBIGUOUS_MATCH", f"{len(hits)} assets match", candidates=[{"id": r["id"], "record_type": t, "name": r.get("hostname") or r.get("resource_name"), "status": r["status"], "last_seen": r.get("last_seen")} for t, r in hits])
        return {"asset": hits[0][1], "record_type": hits[0][0]}

    @tool
    def get_deployment_history(self, asset_id: str) -> dict:
        """Deployment / provisioning history for an asset (pipeline, actor, linked change record)."""
        t, a = self._asset(asset_id)
        rows = sorted(self._where("deployments", asset_id=a["id"]), key=lambda r: r["deployed_at"], reverse=True)
        return {"asset_id": a["id"], "deployments": rows}

    @tool
    def get_change_record(self, change_id: str) -> dict:
        """Change management record (approval, window, scope)."""
        return {"change": self._rec("changes", change_id, "change_id")}

    @tool
    def get_security_alerts(self, asset_id: str) -> dict:
        """Security alerts raised against an asset (EDR / network monitoring)."""
        t, a = self._asset(asset_id)
        return {"asset_id": a["id"], "alerts": sorted(self._where("security_alerts", asset_id=a["id"]), key=lambda r: r["raised_at"], reverse=True)}

    @tool
    def get_employee(self, employee_id: str) -> dict:
        """Employee directory entry (department, employment status, manager)."""
        return {"employee": self._rec("employees", employee_id, "employee_id")}

    @tool
    def get_ticket(self, ticket_id: str) -> dict:
        """Ticketing system record."""
        return {"ticket": self._rec("tickets", ticket_id, "ticket_id")}

    @tool
    def isolate_asset(self, asset_id: str, approval_token: str | None = None) -> dict:
        """[Security, needs approval] Network-isolate an asset (simulated)."""
        t, a = self._asset(asset_id)
        eff = self._sensitive("isolate_asset", {"asset_id": asset_id}, approval_token, {"asset_id": a["id"], "result": "isolated"})
        self.state["isolated"].append({"asset_id": a["id"]})
        return eff

    @tool
    def decommission_asset(self, asset_id: str, approval_token: str | None = None) -> dict:
        """[Security, needs approval] Decommission / terminate an asset (simulated)."""
        t, a = self._asset(asset_id)
        return self._sensitive("decommission_asset", {"asset_id": asset_id}, approval_token, {"asset_id": a["id"], "result": "decommission_simulated"})
