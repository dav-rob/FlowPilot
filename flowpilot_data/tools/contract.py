"""Contract repository, supplier risk, financial controls, privacy assessments and approval workflows."""
from __future__ import annotations

from .core import ToolError, tool


class ContractTools:
    @tool
    def get_contract(self, contract_id: str) -> dict:
        """Contract repository record (value in GBP, term, status, owner, personal-data flag, current version id)."""
        c = self._rec("contracts", contract_id, "contract_id")
        cur = self.env.get(c["current_version_id"]) if c.get("current_version_id") else None
        return {"contract": c, "version_ids": [v["id"] for v in sorted(self._where("contract_versions", contract_id=c["id"]), key=lambda r: r["version_no"])],
                "current_version": cur[1] if cur else None}

    @tool
    def find_contracts(self, supplier_id: str | None = None, contract_number: str | None = None, status: str | None = None) -> dict:
        """Find contracts by supplier, contract number or status."""
        if not any([supplier_id, contract_number, status]):
            raise ToolError("INVALID_ARGUMENT", "provide supplier_id, contract_number or status")
        rows = [c for c in self.env.rows("contracts") if (not supplier_id or c["supplier_id"] == supplier_id)
                and (not contract_number or c["contract_number"].lower() == contract_number.lower()) and (not status or c["status"] == status)]
        if not rows:
            raise ToolError("NOT_FOUND", "No contracts match")
        return {"contracts": rows, "count": len(rows)}

    @tool
    def compare_contract_versions(self, contract_id: str, from_version: int | None = None, to_version: int | None = None) -> dict:
        """Clause-level comparison between two versions of a contract (defaults to the previous and latest versions)."""
        c = self._rec("contracts", contract_id, "contract_id")
        vers = sorted(self._where("contract_versions", contract_id=c["id"]), key=lambda r: r["version_no"])
        if len(vers) < 2:
            raise ToolError("NO_DATA", "Contract has fewer than two versions to compare", version_ids=[v["id"] for v in vers])
        byn = {v["version_no"]: v for v in vers}
        a = byn.get(from_version) if from_version else vers[-2]
        b = byn.get(to_version) if to_version else vers[-1]
        if not a or not b:
            raise ToolError("INVALID_ARGUMENT", "unknown version number", available=sorted(byn))
        diffs = [{"clause": k, "from": a["clauses"].get(k), "to": b["clauses"].get(k)} for k in sorted(set(a["clauses"]) | set(b["clauses"])) if a["clauses"].get(k) != b["clauses"].get(k)]
        return {"contract_id": c["id"], "from_version": {"id": a["id"], "version_no": a["version_no"]}, "to_version": {"id": b["id"], "version_no": b["version_no"], "change_summary": b["change_summary"]}, "changed_clauses": diffs}

    @tool
    def get_supplier_risk(self, supplier_id: str) -> dict:
        """Supplier risk assessments (rating, factors, screening status), current and superseded."""
        s = self._rec("suppliers", supplier_id, "supplier_id")
        return {"supplier_id": s["id"], "assessments": sorted(self._where("supplier_risk", supplier_id=s["id"]), key=lambda r: r["assessed_on"], reverse=True)}

    @tool
    def get_financial_controls(self, contract_id: str) -> dict:
        """Financial controls for a contract: delegated-authority limits for the owner and budget approvals required for its value."""
        c = self._rec("contracts", contract_id, "contract_id")
        owner = self.env.get(c["owner_employee_id"]) if c.get("owner_employee_id") else None
        auth = [a for a in self.env.rows("delegated_authority") if a.get("employee_id") == c.get("owner_employee_id")]
        value = c["annual_value_gbp"] * c["term_months"] / 12
        return {"contract_id": c["id"], "total_contract_value_gbp": value, "owner": owner[1] if owner else None, "delegated_authority": auth,
                "authority_sufficient": bool(auth) and max(a["limit_gbp"] for a in auth) >= value}

    @tool
    def get_privacy_assessment(self, contract_id: str) -> dict:
        """Privacy / data-protection impact assessments linked to a contract or its supplier."""
        c = self._rec("contracts", contract_id, "contract_id")
        rows = [p for p in self.env.rows("privacy_assessments") if p.get("contract_id") == c["id"] or p.get("supplier_id") == c["supplier_id"]]
        return {"contract_id": c["id"], "processes_personal_data": c["processes_personal_data"], "assessments": rows}

    @tool
    def get_approval_workflow(self, contract_id: str) -> dict:
        """Approval workflow instances and step status for a contract."""
        c = self._rec("contracts", contract_id, "contract_id")
        return {"contract_id": c["id"], "workflows": self._where("approval_workflows", contract_id=c["id"])}

    @tool
    def release_contract_for_signature(self, contract_id: str, approval_token: str | None = None) -> dict:
        """[Finance, needs approval] Release the contract for signature (simulated)."""
        c = self._rec("contracts", contract_id, "contract_id")
        return self._sensitive("release_contract_for_signature", {"contract_id": contract_id}, approval_token, {"contract_id": c["id"], "result": "released_for_signature"})
