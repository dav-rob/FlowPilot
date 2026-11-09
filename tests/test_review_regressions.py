"""Regression tests for the independent review findings (synthetic temp fixtures only)."""
import json
import tempfile
import unittest
from pathlib import Path

from flowpilot_data.noise import apply_noise
from flowpilot_data.tools.core import EnterpriseEnv
from flowpilot_data.tools import EnterpriseSession
from flowpilot_data.util import Rng

CASE = "CASE-000001"


def _supplier(sid, name, vat, company, domain):
    return {"id": sid, "name": name, "trading_names": [], "vat_number": vat, "company_number": company,
            "email_domain": domain, "status": "active", "address": "1 Test Row, ZZ1 1ZZ"}


TABLES = {
    "suppliers": [
        _supplier("SUP-AAAAAA01", "Apex Logistics Ltd", "GB000111111", "ZZ111111", "apex.example"),
        _supplier("SUP-AAAAAA02", "Apex Logistics Group", "GB000222222", "ZZ222222", "apexgroup.example"),
    ],
    "email_messages": [
        {"id": "MSG-AAAAAA01", "rfc_message_id": None, "sender": "a@x.example"},
        {"id": "MSG-AAAAAA02", "sender": "b@x.example"},  # header key missing entirely
        {"id": "MSG-AAAAAA03", "rfc_message_id": "Real-1@x.example", "sender": "c@x.example", "reply_to": "c@x.example",
         "verdicts": {}, "analysis": {}, "received_at": "2026-01-01T00:00:00Z"},
    ],
    "supplier_bank_accounts": [{"id": "BAC-AAAAAA01", "supplier_id": "SUP-AAAAAA01", "account_number": "00000000"}],
    "audit_log": [{"id": "LOG-AAAAAA01", "subject_id": "SVC-AAAAAA01", "timestamp": "2026-01-01T00:00:00Z", "summary": "x"},
                  {"id": "LOG-AAAAAA02", "subject_id": "SUP-AAAAAA01", "timestamp": "2026-01-01T00:00:00Z", "summary": "y"}],
    "service_status": [{"id": "SVC-AAAAAA01", "tool": "get_invoice", "scope_case_id": "CASE-OTHER", "mode": "down_for_first_n_calls"}],
}


class ReviewRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        (base / "enterprise").mkdir()
        for table, rows in TABLES.items():
            (base / "enterprise" / f"{table}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (base / "cases.jsonl").write_text(json.dumps({"case_id": CASE}) + "\n", encoding="utf-8")
        cls.session = EnterpriseSession(EnterpriseEnv(base), CASE)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def call(self, tool_name, /, **kw):
        return self.session.call(tool_name, **kw)

    # 1
    def test_protect_is_case_insensitive(self):
        text = " ".join(["Please pay Apex Logistics promptly."] * 200)
        for mode in ("typo", "ocr"):
            for seed in range(3):
                out = apply_noise(text, Rng(seed), 2, mode=mode, protect=frozenset({"Apex", "Logistics"}))
                self.assertEqual(out.count("Apex"), 200, (mode, seed))
                self.assertEqual(out.count("Logistics"), 200, (mode, seed))

    # 2
    def test_find_supplier_accepts_company_number(self):
        r = self.call("find_supplier", name="Apex Logistics")
        self.assertEqual(r["error"]["code"], "AMBIGUOUS_MATCH")
        self.assertIn("company number", r["error"]["message"])
        r = self.call("find_supplier", name="Apex Logistics", company_number=" zz 222222 ")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["data"]["supplier"]["id"], "SUP-AAAAAA02")
        r = self.call("find_supplier", company_number="ZZ999999")
        self.assertEqual(r["error"]["code"], "NOT_FOUND")
        # existing filters keep working
        self.assertEqual(self.call("find_supplier", vat_number="GB000111111")["data"]["supplier"]["id"], "SUP-AAAAAA01")

    # 3
    def test_link_and_audit_lookup_strip_whitespace(self):
        plain = self.call("get_linked_records", record_id="SUP-AAAAAA01")
        padded = self.call("get_linked_records", record_id="  SUP-AAAAAA01 ")
        self.assertTrue(plain["ok"] and padded["ok"])
        self.assertEqual(padded["data"]["record_id"], "SUP-AAAAAA01")
        self.assertEqual(plain["data"]["links"], padded["data"]["links"])
        self.assertTrue(padded["data"]["links"])  # the bank account links back to the supplier
        audit = self.call("get_audit_trail", record_id=" SUP-AAAAAA01\n")
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(audit["data"]["record_id"], "SUP-AAAAAA01")
        self.assertEqual([e["id"] for e in audit["data"]["entries"]], ["LOG-AAAAAA02"])

    # 4
    def test_message_lookup_tolerates_missing_rfc_id(self):
        r = self.call("get_email_headers", message_id="<no-such@x.example>")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "NOT_FOUND")
        self.assertEqual(self.call("get_email_headers", message_id="<>")["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("verify_email_origin", message_id="<real-1@X.example>")["data"]["message_record_id"], "MSG-AAAAAA03")

    # 5
    def test_hidden_service_status_is_not_disclosed(self):
        hidden = self.call("get_supplier_record", supplier_id="SVC-AAAAAA01")
        missing = self.call("get_supplier_record", supplier_id="SVC-FFFFFFFF")
        self.assertEqual(hidden["error"]["code"], "NOT_FOUND")
        self.assertEqual(missing["error"]["code"], "NOT_FOUND")
        self.assertNotIn("service_status", json.dumps(hidden))
        self.assertEqual(self.call("get_audit_trail", record_id="SVC-AAAAAA01")["error"]["code"], "NOT_FOUND")
        self.assertEqual(self.call("get_linked_records", record_id="SVC-AAAAAA01")["error"]["code"], "NOT_FOUND")
        # a visible record of the wrong type still gets the informative error
        self.assertEqual(self.call("get_supplier_record", supplier_id="BAC-AAAAAA01")["error"]["code"], "WRONG_RECORD_TYPE")


if __name__ == "__main__":
    unittest.main()
