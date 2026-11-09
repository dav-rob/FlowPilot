"""Supplier ERP / purchase orders / email authentication / fraud case tools."""
from __future__ import annotations

from .core import ToolError, tool


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace(".", " ").replace(",", " ").replace("-", " ").replace("/", " ").split())


class SupplierTools:
    @tool
    def get_supplier_record(self, supplier_id: str) -> dict:
        """Supplier ERP master record with active bank account and registered contacts."""
        sup = self._rec("suppliers", supplier_id, "supplier_id")
        bank = self.env.get(sup["active_bank_account_id"]) if sup.get("active_bank_account_id") else None
        contacts = self._where("supplier_contacts", supplier_id=sup["id"])
        return {"supplier": sup, "active_bank_account": bank[1] if bank else None, "registered_contacts": contacts}

    @tool
    def find_supplier(self, name: str | None = None, vat_number: str | None = None, email_domain: str | None = None, account_number: str | None = None,
                      company_number: str | None = None) -> dict:
        """Look up supplier master records by name, VAT number, company number, email domain or bank account number. Errors if none or several match."""
        if not any([name, vat_number, email_domain, account_number, company_number]):
            raise ToolError("INVALID_ARGUMENT", "provide at least one of name, vat_number, company_number, email_domain, account_number")
        hits = []
        for s in self.env.rows("suppliers"):
            ok = True
            if name:
                n = _norm(name)
                ok &= any(all(t in _norm(nm) for t in n.split()) for nm in [s["name"]] + list(s.get("trading_names", [])))
            if vat_number:
                ok &= s["vat_number"].replace(" ", "").lower() == vat_number.replace(" ", "").lower()
            if company_number:
                ok &= str(s.get("company_number") or "").replace(" ", "").lower() == company_number.replace(" ", "").lower()
            if email_domain:
                ok &= s["email_domain"].lower() == email_domain.lower().lstrip("@")
            if account_number:
                ok &= any(b["account_number"] == account_number and b["supplier_id"] == s["id"] for b in self.env.rows("supplier_bank_accounts"))
            if ok:
                hits.append(s)
        if not hits:
            raise ToolError("NOT_FOUND", "No supplier matches the given identifiers")
        if len(hits) > 1:
            raise ToolError("AMBIGUOUS_MATCH", f"{len(hits)} suppliers match; refine using VAT number, company number or email domain",
                            candidates=[{"id": s["id"], "name": s["name"], "status": s["status"], "vat_number": s["vat_number"], "address": s["address"]} for s in hits])
        return {"supplier": hits[0]}

    @tool
    def get_supplier_change_history(self, supplier_id: str) -> dict:
        """History of bank-detail and contact change requests for a supplier, including authorisation details, and all bank accounts ever held."""
        sup = self._rec("suppliers", supplier_id, "supplier_id")
        changes = sorted(self._where("supplier_changes", supplier_id=sup["id"]), key=lambda r: r["requested_at"], reverse=True)
        banks = sorted(self._where("supplier_bank_accounts", supplier_id=sup["id"]), key=lambda r: r["added_on"], reverse=True)
        return {"supplier_id": sup["id"], "changes": changes, "bank_accounts": banks}

    @tool
    def get_invoice(self, invoice_id: str) -> dict:
        """Invoice record from accounts payable (amounts in GBP) with payee bank details as stated on the invoice."""
        inv = self._rec("invoices", invoice_id, "invoice_id")
        return {"invoice": inv}

    @tool
    def search_invoices(self, invoice_number: str | None = None, supplier_id: str | None = None, po_number: str | None = None) -> dict:
        """Find invoices by supplier invoice number, supplier id or PO number."""
        if not any([invoice_number, supplier_id, po_number]):
            raise ToolError("INVALID_ARGUMENT", "provide invoice_number, supplier_id or po_number")
        out = []
        for i in self.env.rows("invoices"):
            if invoice_number and _norm(i["invoice_number"]) != _norm(invoice_number):
                continue
            if supplier_id and i["supplier_id"] != supplier_id:
                continue
            if po_number and i.get("po_reference") != po_number and i.get("purchase_order_id") != po_number:
                continue
            out.append(i)
        if not out:
            raise ToolError("NOT_FOUND", "No invoices match")
        return {"matches": out, "count": len(out)}

    @tool
    def get_purchase_order(self, po_id: str) -> dict:
        """Purchase order header and lines (GBP), approver and status."""
        return {"purchase_order": self._rec("purchase_orders", po_id, "po_id")}

    @tool
    def get_goods_receipts(self, po_id: str) -> dict:
        """Goods/service receipts booked against a purchase order."""
        po = self._rec("purchase_orders", po_id, "po_id")
        return {"po_id": po["id"], "receipts": self._where("goods_receipts", purchase_order_id=po["id"])}

    def _msg(self, message_id: str) -> dict:
        self._need(message_id=message_id)
        mid = message_id.strip().strip("<>")
        if not mid:
            raise ToolError("INVALID_ARGUMENT", "message_id must contain a message identifier")
        for m in self.env.rows("email_messages"):
            if m["id"] == mid or (m.get("rfc_message_id") or "").lower() == mid.lower():
                return m
        raise ToolError("NOT_FOUND", f"No gateway record for message {message_id!r}")

    @tool
    def verify_email_origin(self, message_id: str) -> dict:
        """Email gateway authentication verdicts (SPF/DKIM/DMARC, lookalike and reply-to analysis) for a message id."""
        m = dict(self._msg(message_id))
        return {"message_record_id": m["id"], "sender": m["sender"], "reply_to": m["reply_to"], "verdicts": m["verdicts"], "analysis": m["analysis"], "received_at": m["received_at"]}

    @tool
    def get_email_headers(self, message_id: str) -> dict:
        """Raw header fields stored by the mail archive for a message id (no verdict summary)."""
        m = self._msg(message_id)
        return {"message_record_id": m["id"], "headers": m["raw_headers"]}

    @tool
    def get_callback_log(self, supplier_id: str) -> dict:
        """Call-back verification attempts made to suppliers' verified numbers."""
        sup = self._rec("suppliers", supplier_id, "supplier_id")
        return {"supplier_id": sup["id"], "entries": sorted(self._where("callback_log", supplier_id=sup["id"]), key=lambda r: r["performed_at"], reverse=True)}

    @tool
    def get_payment_status(self, invoice_id: str) -> dict:
        """Payment scheduling status for an invoice (payment run, hold flags)."""
        inv = self._rec("invoices", invoice_id, "invoice_id")
        pays = self._where("payments", invoice_id=inv["id"])
        for p in pays:
            if any(h["invoice_id"] == inv["id"] for h in self.state["holds"]):
                p["status"] = "on_hold (simulated)"
        return {"invoice_id": inv["id"], "payments": pays}

    @tool
    def find_account_usage(self, account_number: str, sort_code: str | None = None) -> dict:
        """Where a bank account number is used: supplier bank records and fraud-case beneficiary accounts."""
        self._need(account_number=account_number)
        banks = [b for b in self.env.rows("supplier_bank_accounts") if b["account_number"] == account_number and (not sort_code or b["sort_code"] == sort_code)]
        frauds = [f for f in self.env.rows("fraud_cases") if f.get("beneficiary_account_number") == account_number]
        if not banks and not frauds:
            raise ToolError("NOT_FOUND", "Account number not seen in supplier records or fraud cases")
        return {"account_number": account_number, "bank_records": banks, "fraud_cases": frauds}

    @tool
    def get_fraud_cases(self, supplier_id: str) -> dict:
        """Existing fraud / suspicious-activity cases linked to a supplier."""
        sup = self._rec("suppliers", supplier_id, "supplier_id")
        return {"supplier_id": sup["id"], "cases": self._where("fraud_cases", supplier_id=sup["id"])}

    # -- sensitive (simulated, approval required) --------------------------------
    @tool
    def place_payment_hold(self, invoice_id: str, reason: str, approval_token: str | None = None) -> dict:
        """[Finance, needs approval] Place a simulated hold on the payment for an invoice."""
        self._need(reason=reason)
        inv = self._rec("invoices", invoice_id, "invoice_id")
        eff = self._sensitive("place_payment_hold", {"invoice_id": invoice_id, "reason": reason}, approval_token, {"invoice_id": inv["id"], "result": "hold_placed"})
        self.state["holds"].append({"invoice_id": inv["id"]})
        return eff

    @tool
    def release_payment(self, invoice_id: str, approval_token: str | None = None) -> dict:
        """[Finance, needs approval] Release a scheduled payment for an invoice."""
        inv = self._rec("invoices", invoice_id, "invoice_id")
        return self._sensitive("release_payment", {"invoice_id": invoice_id}, approval_token, {"invoice_id": inv["id"], "result": "payment_released"})

    @tool
    def update_supplier_bank_details(self, supplier_id: str, bank_account_id: str, approval_token: str | None = None) -> dict:
        """[Finance, needs approval] Make a pending bank account the supplier's active account."""
        sup = self._rec("suppliers", supplier_id, "supplier_id")
        bank = self._rec("supplier_bank_accounts", bank_account_id, "bank_account_id")
        if bank["supplier_id"] != sup["id"]:
            raise ToolError("INVALID_ARGUMENT", "bank account does not belong to this supplier")
        return self._sensitive("update_supplier_bank_details", {"supplier_id": supplier_id, "bank_account_id": bank_account_id}, approval_token,
                               {"supplier_id": sup["id"], "result": "bank_details_updated"})
