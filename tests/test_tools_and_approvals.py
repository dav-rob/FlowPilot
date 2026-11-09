"""Mock enterprise tools, dependent discovery paths, outages, session isolation and approval authority tests."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from flowpilot_data.schema import SENSITIVE_TOOLS
from flowpilot_data.tools import ApprovalAuthority, EnterpriseEnv, EnterpriseSession, open_session
from flowpilot_data.util import read_jsonl

REPO_ROOT = Path(__file__).resolve().parent.parent


class ToolsAndApprovalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train_env = EnterpriseEnv(REPO_ROOT / "data" / "partitions" / "train")
        cls.test_env = EnterpriseEnv(REPO_ROOT / "data" / "partitions" / "test")
        cls.train_truth = {t["case_id"]: t for t in read_jsonl(REPO_ROOT / "evaluation" / "ground_truth" / "train.jsonl")}
        cls.train_cases = {c["case_id"]: c for c in read_jsonl(REPO_ROOT / "data" / "partitions" / "train" / "cases.jsonl")}

    def test_partition_scoping_and_in_memory_mutation_isolation(self):
        test_case_id = next(iter(self.test_env.case_ids))
        with self.assertRaises(ValueError):
            EnterpriseSession(self.train_env, test_case_id)

        cid = next(iter(self.train_env.case_ids))
        sup_id = self.train_env.rows("suppliers")[0]["id"]
        s1 = EnterpriseSession(self.train_env, cid)
        s2 = EnterpriseSession(self.train_env, cid)

        r_ticket = s1.call("create_ticket", summary="Investigate supplier anomaly", category="fraud", related_records=[sup_id])
        self.assertTrue(r_ticket["ok"], r_ticket)
        self.assertTrue(r_ticket["data"]["simulated"])
        r_case = s1.call("create_review_case", case_type="fraud", evidence=[sup_id], summary="Follow-up")
        self.assertTrue(r_case["ok"], r_case)

        self.assertEqual(len(s1.state["tickets"]), 1)
        self.assertEqual(len(s1.state["review_cases"]), 1)
        self.assertEqual(len(s2.state["tickets"]), 0)
        self.assertEqual(len(s2.state["review_cases"]), 0)

    def test_structured_tool_errors_and_hidden_service_status_protection(self):
        cid = next(iter(self.train_env.case_ids))
        sess = EnterpriseSession(self.train_env, cid)

        # Unknown tool & invalid arguments
        self.assertEqual(sess.call("nonexistent_tool")["error"]["code"], "UNKNOWN_TOOL")
        self.assertEqual(sess.call("get_supplier_record")["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(sess.call("get_supplier_record", supplier_id="SUP-123", extra_param=1)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(sess.call("search_records", query="test", limit=99)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(sess.call("search_records", query="test", record_types=["service_status"])["error"]["code"], "INVALID_ARGUMENT")

        # Wrong record type vs not found
        inv_id = self.train_env.rows("invoices")[0]["id"]
        wrong = sess.call("get_supplier_record", supplier_id=inv_id)
        self.assertFalse(wrong["ok"])
        self.assertEqual(wrong["error"]["code"], "WRONG_RECORD_TYPE")
        self.assertEqual(sess.call("get_supplier_record", supplier_id="SUP-FFFFFFFF")["error"]["code"], "NOT_FOUND")

        # Hidden service_status is rejected in both create_review_case and create_ticket
        svc_id = self.train_env.rows("service_status")[0]["id"]
        self.assertEqual(
            sess.call("create_review_case", case_type="other", evidence=[svc_id])["error"]["code"],
            "INVALID_EVIDENCE",
        )
        self.assertEqual(
            sess.call("create_ticket", summary="Check status", related_records=[svc_id])["error"]["code"],
            "INVALID_EVIDENCE",
        )

    def test_dependent_multi_step_discovery_and_async_acall(self):
        # Showcase case IN-B148DF6144: incoming doc has invoice_number SI-79253, not SUP-47D4A998 or MSG-0C0E250E
        cid = "IN-B148DF6144"
        doc_rel = self.train_cases[cid]["document"]["path"]
        doc_text = (REPO_ROOT / "data" / "partitions" / "train" / doc_rel).read_text(encoding="utf-8")
        self.assertIn("SI-79253", doc_text)
        self.assertNotIn("SUP-47D4A998", doc_text)
        self.assertNotIn("MSG-0C0E250E", doc_text)

        sess = open_session(REPO_ROOT / "data", "train", cid)
        step1 = asyncio.run(sess.acall("search_invoices", invoice_number="SI-79253"))
        self.assertTrue(step1["ok"], step1)
        inv = step1["data"]["matches"][0]
        self.assertEqual(inv["supplier_id"], "SUP-47D4A998")
        self.assertEqual(inv["source_message_id"], "MSG-0C0E250E")

        step2 = asyncio.run(sess.acall("get_supplier_record", supplier_id=inv["supplier_id"]))
        self.assertTrue(step2["ok"], step2)
        self.assertEqual(step2["data"]["supplier"]["onboarding_checks"], "incomplete")

        # Step 3 hits a deterministic transient outage for first 2 calls on IN-B148DF6144, then recovers on call 3
        a1 = sess.call("verify_email_origin", message_id=inv["source_message_id"])
        a2 = sess.call("verify_email_origin", message_id=inv["source_message_id"])
        a3 = sess.call("verify_email_origin", message_id=inv["source_message_id"])
        self.assertFalse(a1["ok"])
        self.assertEqual(a1["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertTrue(a1["error"]["retryable"])
        self.assertFalse(a2["ok"])
        self.assertTrue(a3["ok"], a3)
        self.assertEqual(a3["data"]["message_record_id"], "MSG-0C0E250E")

    def test_persistent_outage_recoverable_via_alternate_tool(self):
        # Find a case in train with a persistent `down_with_alternate` outage
        alt_cases = [
            t for t in self.train_truth.values()
            if any(u["mode"] == "down_with_alternate" for u in t["discoverability"]["unavailable_services"])
        ]
        self.assertTrue(alt_cases, "expected at least one down_with_alternate case in train")
        t = alt_cases[0]
        unavail = next(u for u in t["discoverability"]["unavailable_services"] if u["mode"] == "down_with_alternate")
        blocked_path = next(p for p in t["discoverability"]["paths"] if p.get("blocked"))
        failing_step = next(s for s in blocked_path["steps"] if s["tool"] == unavail["tool"])

        sess = EnterpriseSession(self.train_env, t["case_id"])
        res1 = sess.call(failing_step["tool"], **failing_step["args"])
        res2 = sess.call(failing_step["tool"], **failing_step["args"])
        self.assertFalse(res1["ok"])
        self.assertEqual(res1["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertFalse(res1["error"]["retryable"])
        self.assertFalse(res2["ok"])

        # Non-blocked path still succeeds on the same session
        good_path = next(p for p in t["discoverability"]["paths"] if not p.get("blocked"))
        for step in good_path["steps"]:
            r = sess.call(step["tool"], **step["args"])
            if not r["ok"] and r["error"]["code"] == "SERVICE_UNAVAILABLE" and r["error"].get("retryable"):
                r = sess.call(step["tool"], **step["args"])
                if not r["ok"]:
                    r = sess.call(step["tool"], **step["args"])
            self.assertTrue(r["ok"], r)

    def test_approval_authority_enforces_scope_signature_and_single_use(self):
        cases = list(self.train_env.case_ids)
        cid_a, cid_b = cases[0], cases[1]
        auth = ApprovalAuthority()
        sess_a = EnterpriseSession(self.train_env, cid_a, authority=auth)
        sess_b = EnterpriseSession(self.train_env, cid_b, authority=auth)

        inv_id = self.train_env.rows("invoices")[0]["id"]
        sup = self.train_env.rows("suppliers")[0]
        bac_id = next(b["id"] for b in self.train_env.rows("supplier_bank_accounts") if b["supplier_id"] == sup["id"])
        acg_id = self.train_env.rows("access_grants")[0]["id"]
        ci_id = self.train_env.rows("cmdb_items")[0]["id"]
        loc = self.train_env.rows("data_locations")[0]
        cus_id, dst_id = loc["customer_id"], loc["dataset_id"]
        ctr_id = self.train_env.rows("contracts")[0]["id"]

        sample_calls = {
            "place_payment_hold": {"invoice_id": inv_id, "reason": "Suspected fraud"},
            "release_payment": {"invoice_id": inv_id},
            "update_supplier_bank_details": {"supplier_id": sup["id"], "bank_account_id": bac_id},
            "revoke_access_grant": {"grant_id": acg_id},
            "isolate_asset": {"asset_id": ci_id},
            "decommission_asset": {"asset_id": ci_id},
            "execute_erasure": {"customer_id": cus_id, "dataset_ids": [dst_id]},
            "export_customer_data": {"customer_id": cus_id, "dataset_ids": [dst_id]},
            "update_customer_record": {"customer_id": cus_id, "changes": {"postcode": "ZZ9 9ZZ"}},
            "release_contract_for_signature": {"contract_id": ctr_id},
        }
        self.assertEqual(set(sample_calls), set(SENSITIVE_TOOLS))

        # Every sensitive tool rejects unapproved execution and forged tokens
        for tool_name, call_args in sample_calls.items():
            res = sess_a.call(tool_name, **call_args)
            self.assertFalse(res["ok"], tool_name)
            self.assertEqual(res["error"]["code"], "APPROVAL_REQUIRED")

            forged = sess_a.call(tool_name, **call_args, approval_token="eyJmb3JnZWQiOnRydWV9.deadbeef")
            self.assertFalse(forged["ok"], tool_name)
            self.assertEqual(forged["error"]["code"], "APPROVAL_INVALID")

        # Submit an approval request, verify pending state, then approve
        target_args = {"invoice_id": inv_id, "reason": "Confirmed executive impersonation"}
        req_res = sess_a.call("request_approval", action="place_payment_hold", arguments=target_args, justification="Spoofed email")
        self.assertTrue(req_res["ok"], req_res)
        req_id = req_res["data"]["request_id"]
        self.assertEqual(req_res["data"]["status"], "pending")
        self.assertEqual(len(auth.pending()), 1)

        token = auth.decide(req_id, approve=True, approver="fraud-lead")
        self.assertIsNotNone(token)
        self.assertEqual(len(auth.pending()), 0)

        # Wrong case, wrong tool, or modified arguments -> APPROVAL_WRONG_SCOPE
        self.assertEqual(
            sess_b.call("place_payment_hold", **target_args, approval_token=token)["error"]["code"],
            "APPROVAL_WRONG_SCOPE",
        )
        self.assertEqual(
            sess_a.call("release_payment", invoice_id=inv_id, approval_token=token)["error"]["code"],
            "APPROVAL_WRONG_SCOPE",
        )
        self.assertEqual(
            sess_a.call("place_payment_hold", invoice_id=inv_id, reason="Modified reason", approval_token=token)["error"]["code"],
            "APPROVAL_WRONG_SCOPE",
        )

        # Exact scope succeeds once and records simulated state
        ok_res = sess_a.call("place_payment_hold", **target_args, approval_token=token)
        self.assertTrue(ok_res["ok"], ok_res)
        self.assertTrue(ok_res["data"]["simulated"])
        self.assertEqual(len(sess_a.state["actions"]), 1)

        # Replaying the consumed token fails with APPROVAL_REUSED
        replay = sess_a.call("place_payment_hold", **target_args, approval_token=token)
        self.assertFalse(replay["ok"])
        self.assertEqual(replay["error"]["code"], "APPROVAL_REUSED")


if __name__ == "__main__":
    unittest.main()
