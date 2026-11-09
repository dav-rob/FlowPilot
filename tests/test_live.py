"""Opt-in real CLI checks. Run FLOWPILOT_LIVE_TESTS=1 pytest tests/test_live.py -v.

These exercise genuine structured model-selected tools, rather than a scripted policy.
The synthetic tool observation changes while the input and instructions stay fixed.
"""

import json
import os
import pytest
from flowpilot.engine import ACTION_SCHEMA, SYSTEM, step_semantic_error
from flowpilot.registry import Registry
from flowpilot.catalog import ROOT
from flowpilot_data.tools import open_session

pytestmark = pytest.mark.skipif(
    os.getenv("FLOWPILOT_LIVE_TESTS") != "1",
    reason="Requires authenticated local CLI subscriptions",
)


@pytest.mark.asyncio
async def test_real_model_changes_action_when_bank_evidence_changes():
    from flowpilot.models import ModelRouter

    router = ModelRouter()
    registry = Registry(
        open_session(ROOT / "data", "train", "IN-B148DF6144"), ["supplier_fraud"]
    )
    # Narrow focus is a legitimate runtime budget, not a predefined execution path.
    tools = [
        t
        for t in registry.describe()
        if t["name"]
        in (
            "get_supplier_change_history",
            "get_callback_log",
            "request_approval",
            "create_review_case",
        )
    ]
    decisions = []
    for account in ("12345678", "98765432"):
        obs = [
            {
                "tool": "get_invoice",
                "arguments": {"invoice_id": "INV-00000001"},
                "result": {
                    "ok": True,
                    "tool": "get_invoice",
                    "data": {
                        "invoice": {
                            "id": "INV-00000001",
                            "supplier_id": "SUP-00000001",
                            "remit_to": {
                                "account_number": account,
                                "sort_code": "00-00-01",
                            },
                            "total_gbp": 200,
                            "status": "awaiting_payment",
                        }
                    },
                },
            },
            {
                "tool": "get_supplier_record",
                "arguments": {"supplier_id": "SUP-00000001"},
                "result": {
                    "ok": True,
                    "tool": "get_supplier_record",
                    "data": {
                        "supplier": {
                            "id": "SUP-00000001",
                            "name": "Example Supplier Ltd",
                            "onboarding_checks": "complete",
                            "status": "active",
                        },
                        "active_bank_account": {
                            "id": "BAC-00000001",
                            "account_number": "12345678",
                            "sort_code": "00-00-01",
                        },
                    },
                },
            },
            {
                "tool": "verify_email_origin",
                "arguments": {"message_id": "MSG-00000001"},
                "result": {
                    "ok": True,
                    "tool": "verify_email_origin",
                    "data": {
                        "message_record_id": "MSG-00000001",
                        "verdicts": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
                        "analysis": "No lookalike or reply-to discrepancy.",
                    },
                },
            },
            {
                "tool": "get_purchase_order",
                "arguments": {"po_id": "PO-00000001"},
                "result": {
                    "ok": True,
                    "tool": "get_purchase_order",
                    "data": {
                        "purchase_order": {
                            "id": "PO-00000001",
                            "status": "approved",
                            "total_gbp": 200,
                        },
                        "goods_received": True,
                        "invoice_matches": True,
                    },
                },
            },
        ]
        payload = {
            "document": "Please investigate invoice INV-00000001 for Example Supplier Ltd. No bank change was declared. Check the supplied enterprise observations for any discrepancy. Conclude if the verified records agree; investigate further where the returned evidence warrants it. Do not request payment execution.",
            "routing": {"categories": ["supplier_fraud"], "primary": "supplier_fraud"},
            "permitted_tools": tools,
            "observations": obs,
            "budget_remaining": {"iterations": 3, "tool_calls": 4},
        }
        for _ in range(3):
            response = await router.complete(
                "investigation", SYSTEM, payload, ACTION_SCHEMA
            )
            error = step_semantic_error(response.data)
            if not error:
                break
            payload["runtime_validation_feedback"] = error
        assert not error, response.data
        decisions.append(response.data)
    assert decisions[0]["kind"] == "finish", json.dumps(decisions)
    assert decisions[1]["kind"] == "calls", json.dumps(decisions)
    assert any(
        a["tool"]
        in ("get_supplier_change_history", "get_callback_log", "create_review_case")
        for a in decisions[1]["actions"]
    ), json.dumps(decisions)
    assert all(a["tool"] in {t["name"] for t in tools} for a in decisions[1]["actions"])
