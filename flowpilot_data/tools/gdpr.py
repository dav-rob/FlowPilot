"""CRM, identity verification, data catalogue, retention and legal hold tools (synthetic rules)."""
from __future__ import annotations

from ..util import REFERENCE_NOW
from .core import ToolError, tool


def _toks(s: str) -> set[str]:
    return set(s.lower().replace(",", " ").replace(".", " ").split())


class GdprTools:
    @tool
    def find_customer(self, full_name: str | None = None, email: str | None = None, postcode: str | None = None,
                      date_of_birth: str | None = None, customer_reference: str | None = None) -> dict:
        """Find a CRM customer by name, email, postcode, date of birth or customer reference. Errors if none or several match."""
        if not any([full_name, email, postcode, date_of_birth, customer_reference]):
            raise ToolError("INVALID_ARGUMENT", "provide at least one identifier")
        hits = []
        for c in self.env.rows("customers"):
            ok = True
            if full_name:
                names = [c["full_name"]] + list(c.get("previous_names", []))
                ok &= any(_toks(full_name) <= _toks(n) for n in names)
            if email:
                ok &= c["email"].lower() == email.lower()
            if postcode:
                ok &= c["postcode"].replace(" ", "").lower() == postcode.replace(" ", "").lower()
            if date_of_birth:
                ok &= c["date_of_birth"] == date_of_birth
            if customer_reference:
                ok &= c["customer_reference"].lower() == customer_reference.lower()
            if ok:
                hits.append(c)
        if not hits:
            raise ToolError("NOT_FOUND", "No customer matches the supplied identifiers")
        if len(hits) > 1:
            raise ToolError("AMBIGUOUS_MATCH", f"{len(hits)} customers match; add distinguishing identifiers",
                            candidates=[{"id": c["id"], "full_name": c["full_name"], "postcode": c["postcode"], "status": c["status"]} for c in hits])
        return {"customer": hits[0]}

    @tool
    def get_customer_record(self, customer_id: str) -> dict:
        """CRM customer record with products and flags."""
        c = self._rec("customers", customer_id, "customer_id")
        return {"customer": c, "products": self._where("customer_products", customer_id=c["id"])}

    @tool
    def verify_identity_status(self, customer_id: str) -> dict:
        """Identity verification checks recorded for a customer (method, outcome, expiry, whether tied to a specific request)."""
        c = self._rec("customers", customer_id, "customer_id")
        rows = sorted(self._where("identity_verifications", customer_id=c["id"]), key=lambda r: r["checked_on"], reverse=True)
        for r in rows:
            r["expired"] = r["expires_on"] < REFERENCE_NOW.strftime("%Y-%m-%d")
        return {"customer_id": c["id"], "verifications": rows}

    @tool
    def find_customer_data(self, customer_id: str) -> dict:
        """Data catalogue: datasets and systems that hold records for a customer."""
        c = self._rec("customers", customer_id, "customer_id")
        out = []
        for loc in self._where("data_locations", customer_id=c["id"]):
            ds = self.env.get(loc["dataset_id"])
            out.append({**loc, "dataset": ds[1] if ds else None})
        if not out:
            raise ToolError("NOT_FOUND", "No data locations catalogued for this customer", customer_id=c["id"])
        return {"customer_id": c["id"], "locations": out}

    @tool
    def get_retention_records(self, customer_id: str) -> dict:
        """Retention schedule status for each dataset holding the customer's data (synthetic fixture rules)."""
        c = self._rec("customers", customer_id, "customer_id")
        out = []
        for loc in self._where("data_locations", customer_id=c["id"]):
            ds = self.env.get(loc["dataset_id"])
            rule = self.env.get(ds[1]["retention_rule_id"]) if ds and ds[1].get("retention_rule_id") else None
            if not rule:
                out.append({"data_location_id": loc["id"], "dataset_id": loc["dataset_id"], "retention_rule": None, "note": "no retention rule assigned"})
                continue
            r = rule[1]
            out.append({"data_location_id": loc["id"], "dataset_id": loc["dataset_id"], "retention_rule": r,
                        "retention_trigger_date": loc["retention_trigger_date"], "eligible_for_erasure_on": loc.get("eligible_for_erasure_on"),
                        "retention_elapsed": (loc.get("eligible_for_erasure_on") or "9999") <= REFERENCE_NOW.strftime("%Y-%m-%d")})
        return {"customer_id": c["id"], "retention": out}

    @tool
    def check_legal_holds(self, customer_id: str) -> dict:
        """Legal holds (active and released) that cover a customer's records."""
        c = self._rec("customers", customer_id, "customer_id")
        return {"customer_id": c["id"], "holds": self._where("legal_holds", customer_id=c["id"])}

    @tool
    def get_data_request_history(self, customer_id: str) -> dict:
        """Previous and open data-subject requests, complaints and outcomes for a customer."""
        c = self._rec("customers", customer_id, "customer_id")
        return {"customer_id": c["id"], "requests": sorted(self._where("data_requests", customer_id=c["id"]), key=lambda r: r["received_on"], reverse=True)}

    @tool
    def get_third_party_authority(self, customer_id: str) -> dict:
        """Authority letters / powers of attorney recorded for third parties acting for a customer."""
        c = self._rec("customers", customer_id, "customer_id")
        rows = self._where("authority_letters", customer_id=c["id"])
        for r in rows:
            r["expired"] = r["valid_until"] < REFERENCE_NOW.strftime("%Y-%m-%d")
        return {"customer_id": c["id"], "authorities": rows}

    # -- sensitive (simulated, approval required) -------------------------------
    def _datasets(self, customer_id: str, dataset_ids: list) -> list[str]:
        c = self._rec("customers", customer_id, "customer_id")
        if not isinstance(dataset_ids, list) or not dataset_ids:
            raise ToolError("INVALID_ARGUMENT", "dataset_ids must be a non-empty list")
        held = {l["dataset_id"] for l in self._where("data_locations", customer_id=c["id"])}
        bad = [d for d in dataset_ids if d not in held]
        if bad:
            raise ToolError("INVALID_ARGUMENT", "datasets do not hold this customer's data", dataset_ids=bad)
        return dataset_ids

    @tool
    def export_customer_data(self, customer_id: str, dataset_ids: list, approval_token: str | None = None) -> dict:
        """[Data disclosure, needs approval] Compile a simulated subject-access export for the listed datasets."""
        ds = self._datasets(customer_id, dataset_ids)
        return self._sensitive("export_customer_data", {"customer_id": customer_id, "dataset_ids": dataset_ids}, approval_token, {"customer_id": customer_id, "datasets": ds, "result": "export_compiled"})

    @tool
    def execute_erasure(self, customer_id: str, dataset_ids: list, approval_token: str | None = None) -> dict:
        """[Deletion, needs approval] Erase the customer's records in the listed datasets (simulated; nothing is deleted)."""
        ds = self._datasets(customer_id, dataset_ids)
        return self._sensitive("execute_erasure", {"customer_id": customer_id, "dataset_ids": dataset_ids}, approval_token, {"customer_id": customer_id, "datasets": ds, "result": "erasure_simulated"})

    @tool
    def update_customer_record(self, customer_id: str, changes: dict, approval_token: str | None = None) -> dict:
        """[Data change, needs approval] Apply field changes (e.g. address, name) to the CRM record (simulated)."""
        c = self._rec("customers", customer_id, "customer_id")
        if not isinstance(changes, dict) or not changes:
            raise ToolError("INVALID_ARGUMENT", "changes must be a non-empty object")
        return self._sensitive("update_customer_record", {"customer_id": customer_id, "changes": changes}, approval_token, {"customer_id": c["id"], "result": "record_updated"})
