"""Policy repository, system inventory, security controls, database queries, audit management."""
from __future__ import annotations

from .core import ToolError, tool

QUERIES = {
    "encryption_status": ["encrypted_at_rest", "encryption_key_age_days"],
    "log_retention": ["log_retention_days"],
    "backup_recency": ["last_backup_hours"],
    "customer_data_summary": ["customer_pii_tables", "row_count"],
    "privileged_access_summary": ["privileged_accounts_total", "privileged_accounts_without_mfa", "last_access_review_days"],
}


class ComplianceTools:
    @tool
    def get_policy(self, policy_id: str) -> dict:
        """Policy repository entry (policy or regulatory notice) with clauses, applicability criteria and version status. Synthetic fixture content."""
        return {"policy": self._rec("policies", policy_id, "policy_id")}

    @tool
    def discover_affected_systems(self, policy_id: str) -> dict:
        """Evaluate a policy's applicability criteria against the system inventory. Lists in-scope systems, systems that need classification review, and near-miss exclusions."""
        pol = self._rec("policies", policy_id, "policy_id")
        crit = pol.get("applicability", {})
        scoped, review, excluded = [], [], []
        for s in self.env.rows("systems"):
            if crit.get("estates") and s.get("estate") not in crit["estates"]:
                continue
            reasons = []
            unknown = False
            for attr, key in (("data_classification", "data_classification"), ("hosting", "hosting"), ("criticality", "criticality")):
                want = crit.get(key)
                if not want:
                    continue
                have = s.get(attr)
                if have in (None, "unclassified"):
                    unknown = True
                elif have in want:
                    reasons.append(f"{attr}={have}")
                else:
                    reasons.append(None)
            row = {"id": s["id"], "name": s["name"], "lifecycle": s["lifecycle"], "match_reasons": [r for r in reasons if r]}
            if s["lifecycle"] == "decommissioned":
                excluded.append({**row, "excluded_because": "system is decommissioned"})
            elif None in reasons:
                excluded.append({**row, "excluded_because": "attributes outside policy criteria"})
            elif unknown:
                review.append({**row, "note": "classification attribute missing; applicability cannot be determined from inventory"})
            else:
                scoped.append(row)
        return {"policy_id": pol["id"], "criteria": crit, "in_scope": scoped, "needs_classification_review": review, "excluded": excluded}

    @tool
    def get_system(self, system_id: str) -> dict:
        """System inventory record with owner and database ids."""
        s = self._rec("systems", system_id, "system_id")
        return {"system": s, "database_ids": [d["id"] for d in self._where("databases", system_id=s["id"])]}

    @tool
    def inspect_security_controls(self, system_id: str) -> dict:
        """Implemented security controls for a system with status, last test date and evidence reference."""
        s = self._rec("systems", system_id, "system_id")
        ctls = self._where("controls", system_id=s["id"])
        for c in ctls:
            cat = self.env.get(c["control_catalogue_id"])
            c["control_title"] = cat[1]["title"] if cat else None
        return {"system_id": s["id"], "controls": ctls}

    @tool
    def get_control_definition(self, control_id: str) -> dict:
        """Control catalogue definition (objective, test procedure)."""
        return {"control": self._rec("control_catalogue", control_id, "control_id")}

    @tool
    def list_system_databases(self, system_id: str) -> dict:
        """Databases registered against a system."""
        s = self._rec("systems", system_id, "system_id")
        return {"system_id": s["id"], "databases": [{k: v for k, v in d.items() if k != "facts"} for d in self._where("databases", system_id=s["id"])]}

    @tool
    def run_database_query(self, database_id: str, query_name: str, parameters: dict | None = None) -> dict:
        """Run a pre-approved read-only configuration query against a database: encryption_status, log_retention, backup_recency, customer_data_summary, privileged_access_summary."""
        db = self._rec("databases", database_id, "database_id")
        if query_name not in QUERIES:
            raise ToolError("INVALID_ARGUMENT", f"unknown query_name {query_name!r}", allowed=sorted(QUERIES))
        facts = db["facts"]
        res = {k: facts.get(k) for k in QUERIES[query_name]}
        if all(v is None for v in res.values()):
            raise ToolError("NO_DATA", f"{query_name} is not collected for {db['name']}", database_id=db["id"])
        return {"database_id": db["id"], "database_name": db["name"], "query_name": query_name, "result": res, "collected_at": facts.get("collected_at")}

    @tool
    def get_access_grants(self, system_id: str, privileged_only: bool = False) -> dict:
        """Access grants on a system (principal, role, MFA, account type, last review)."""
        s = self._rec("systems", system_id, "system_id")
        rows = self._where("access_grants", system_id=s["id"])
        if privileged_only:
            rows = [r for r in rows if r.get("privileged")]
        return {"system_id": s["id"], "grants": rows}

    @tool
    def get_audit_findings(self, system_id: str) -> dict:
        """Audit management: findings (open and closed) raised against a system."""
        s = self._rec("systems", system_id, "system_id")
        return {"system_id": s["id"], "findings": sorted(self._where("audit_findings", system_id=s["id"]), key=lambda r: r["raised_on"], reverse=True)}

    @tool
    def get_control_exceptions(self, system_id: str) -> dict:
        """Approved control exceptions for a system with expiry dates."""
        s = self._rec("systems", system_id, "system_id")
        return {"system_id": s["id"], "exceptions": self._where("control_exceptions", system_id=s["id"])}

    @tool
    def revoke_access_grant(self, grant_id: str, approval_token: str | None = None) -> dict:
        """[Security, needs approval] Revoke an access grant (simulated)."""
        g = self._rec("access_grants", grant_id, "grant_id")
        return self._sensitive("revoke_access_grant", {"grant_id": grant_id}, approval_token, {"grant_id": g["id"], "result": "revoked"})
