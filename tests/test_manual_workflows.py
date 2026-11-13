"""A human handoff is durable, scoped and independent of AI execution."""

import asyncio
import copy
import pytest
from fastapi.testclient import TestClient
from flowpilot.api import create_app
from flowpilot.catalog import ROOT
from flowpilot.engine import Engine, public_run
from flowpilot.manual import create_reviews, route
from flowpilot.store import Store


def outcome(code, departments=None):
    return dict(
        summary="The amendment changes hosting arrangements.",
        conclusion="A departmental decision is needed before proceeding.",
        risk="medium",
        outcome_code=code,
        evidence=[{"record_id": "CON-ABCDEF12", "note": "Observed amendment."}],
        unresolved=[],
        recommendations=["Review the amendment."],
        requires_approval=False,
        actions=[],
        departments=departments or [],
    )


def prepared(engine, code="block_pending_privacy_assessment", departments=None):
    run = engine.create(
        case_id="IN-B148DF6144",
        partition="train",
        document="Contract amendment",
        mode="live",
        title="Hosting amendment",
    )
    run["classification"] = {
        "primary": "contract_risk",
        "categories": ["contract_risk"],
    }
    run["status"] = "running"
    engine.finish(run, outcome(code, departments), {"CON-ABCDEF12"})
    engine.store.put("run", run)
    return run


def test_privacy_handoff_is_durable_and_approval_does_not_execute_change(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    engine = Engine(store)
    run = prepared(engine, departments=["Finance", "Privacy", "Security"])
    assert run["status"] == "awaiting_approval"
    assert [r["department"] for r in run["manual_reviews"]] == ["Privacy"]
    assert run["approvals"] == []
    assert public_run(run)["business_route"]["path"] == "human_review"
    assert run["ruleset_version"] and run["application_revision"]
    request = run["manual_reviews"][0]["request_id"]
    approved = asyncio.run(
        engine.decide_review(
            run["id"], request, True, "Approved subject to the documented controls."
        )
    )
    assert approved["manual_reviews"][0]["status"] == "approved"
    assert approved["status"] == "completed"
    assert "_state" not in approved
    assert store.get("run", run["id"])["_state"] is None
    assert not any(e["kind"] == "tool_result" for e in approved["events"])
    assert approved["events"][-1]["result"]["business_change_executed"] is False
    with pytest.raises(ValueError, match="already been decided"):
        asyncio.run(engine.decide_review(run["id"], request, False, "Second decision"))
    store.close()
    reopened = Store(tmp_path / "state.sqlite3")
    assert reopened.get("run", run["id"])["manual_reviews"][0][
        "decision_note"
    ].startswith("Approved")
    reopened.close()


def test_selective_department_reviews_all_required_and_declines_preserved(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    engine = Engine(store)
    run = prepared(engine, "route_for_standard_approval", ["Finance", "Legal"])
    assert [r["department"] for r in run["manual_reviews"]] == ["Finance", "Legal"]
    first, second = run["manual_reviews"]
    one = asyncio.run(
        engine.decide_review(run["id"], first["request_id"], True, "Finance agrees")
    )
    assert one["status"] == "awaiting_approval"
    two = asyncio.run(
        engine.decide_review(
            run["id"], second["request_id"], False, "Liability terms need revision"
        )
    )
    assert two["status"] == "completed"
    assert two["business_route"]["path"] == "declined"
    assert two["manual_reviews"][1]["status"] == "denied"
    store.close()


def test_incomplete_replay_and_empty_note_cannot_decide(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    engine = Engine(store)
    run = prepared(engine)
    request = run["manual_reviews"][0]["request_id"]
    for status in ("failed", "running", "cancelled"):
        run["status"] = status
        store.put("run", run)
        with pytest.raises(ValueError, match="successfully completed"):
            asyncio.run(engine.decide_review(run["id"], request, True, "Approved"))
    run["status"] = "awaiting_approval"
    store.put("run", run)
    with pytest.raises(ValueError, match="decision note"):
        asyncio.run(engine.decide_review(run["id"], request, True, "  "))
    replay = engine.replay(run["id"])
    with pytest.raises(ValueError, match="successfully completed"):
        asyncio.run(engine.decide_review(replay["id"], request, True, "Approved"))
    store.close()


def test_saved_handoff_enrolment_appends_current_event_without_rewriting_old_trace(
    tmp_path,
):
    store = Store(tmp_path / "state.sqlite3")
    engine = Engine(store)
    run = prepared(engine)
    del run["manual_reviews"]
    run.pop("ruleset_version")
    run.pop("application_revision")
    run["status"] = "completed"
    old_events = copy.deepcopy(run["events"])
    store.put("run", run)
    engine.enroll_saved_reviews()
    enrolled = store.get("run", run["id"])
    assert enrolled["review_execution_status"] == "completed"
    assert enrolled["events"][:-1] == old_events
    assert "ruleset_version" not in enrolled
    assert enrolled["manual_reviews"][0]["origin"] == "enrolled_from_saved_findings"
    engine.enroll_saved_reviews()
    assert store.get("run", run["id"])["events"] == enrolled["events"]
    store.close()


def test_default_route_and_department_recommendations_do_not_create_approval():
    run = dict(
        mode="live",
        status="completed",
        outcome=outcome("no_action_required", ["Finance", "Legal"]),
    )
    assert not create_reviews(run)
    assert run["manual_reviews"] == []
    assert route(run)["path"] == "default"


def test_approval_queue_api_and_decision_history(tmp_path):
    with TestClient(create_app(ROOT, tmp_path)) as client:
        run = prepared(client.app.state.engine)
        items = client.get("/api/approvals").json()["items"]
        assert len(items) == 1 and items[0]["can_decide"]
        url = f"/api/approvals/{run['id']}/{items[0]['request_id']}"
        assert (
            client.post(url, json={"decision": "approve", "note": " "}).status_code
            == 409
        )
        response = client.post(
            url,
            json={"decision": "decline", "note": "Transfer safeguards are missing."},
        )
        assert response.status_code == 200, response.text
        assert response.json()["item"]["status"] == "denied"
        assert response.json()["run"]["business_route"]["path"] == "declined"
        assert (
            client.post(
                url, json={"decision": "approve", "note": "Another decision"}
            ).status_code
            == 409
        )
        assert (
            client.get("/api/approvals")
            .json()["items"][0]["decision_note"]
            .startswith("Transfer")
        )
        test_run = prepared(client.app.state.engine)
        test_run["purpose"] = "evaluation"
        client.app.state.store.put("run", test_run)
        assert len(client.get("/api/approvals").json()["items"]) == 1
        assert len(client.get("/api/approvals?include_tests=true").json()["items"]) == 2


def test_assurance_api_records_actual_results_without_business_mutation(tmp_path):
    with TestClient(create_app(ROOT, tmp_path)) as client:
        assert client.get("/api/assurance").json()["suite"] is None
        result = client.post("/api/assurance/run")
        assert result.status_code == 200, result.text
        assert result.json()["failed"] == 0
        assert result.json()["total"] >= 18
        assert client.get("/api/runs").json()["runs"] == []
        assert client.get("/api/assurance").json()["suite"]["id"] == result.json()["id"]


def test_secondary_privacy_outcome_still_opens_a_gate():
    o = outcome("open_audit_item_gap_found", ["Compliance"])
    o["by_workflow"] = {
        "regulatory_compliance": "open_audit_item_gap_found",
        "contract_risk": "block_pending_privacy_assessment",
    }
    run = dict(mode="live", status="completed", outcome=o)
    assert create_reviews(run)
    assert run["manual_reviews"][0]["department"] == "Privacy"


def test_cancel_closes_pending_department_workflows(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    engine = Engine(store)
    run = prepared(engine)
    cancelled = asyncio.run(engine.cancel(run["id"]))
    assert cancelled["status"] == "cancelled"
    assert cancelled["manual_reviews"][0]["status"] == "denied"
    assert store.get("run", run["id"])["manual_reviews"][0]["decision_note"]
    store.close()


def test_scoring_saved_ai_reviews_creates_analysis_without_rerunning_or_changing_case(
    tmp_path, monkeypatch
):
    from flowpilot.models import ModelRouter

    with TestClient(create_app(ROOT, tmp_path)) as client:
        r = prepared(client.app.state.engine)
        before = client.get("/api/runs/" + r["id"]).json()

        def forbidden(*args, **kwargs):
            raise AssertionError("Scoring saved reviews must not call AI")

        monkeypatch.setattr(ModelRouter, "__init__", forbidden)
        response = client.post("/api/evaluations/recorded", json={})
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["source"] == "saved_ai_reviews" and result["new_model_calls"] == 0
        assert result["completed"] == 1
        row = result["results"][0]
        assert (
            row["expected_outcome"]
            and row["actual_outcome"] == "block_pending_privacy_assessment"
        )
        assert row["models"] == [] and row["outcome_correct"] is False
        assert row["ruleset_version"] == before["ruleset_version"]
        assert client.get("/api/runs/" + r["id"]).json() == before
        assert len(client.get("/api/runs").json()["runs"]) == 1
        assert "No new AI" in result["warning"]
