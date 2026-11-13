"""Guardrail reporting measures actual controls without invoking paid models."""

import copy
import json

import pytest

from flowpilot.assurance import RULESET_VERSION, assurance_report, run_guardrail_suite
from flowpilot.store import Store


@pytest.fixture
def store(tmp_path):
    obj = Store(tmp_path / "assurance.sqlite3")
    yield obj
    obj.close()


def test_catalogue_does_not_invent_results_or_live_coverage(store):
    report = assurance_report(store)
    assert report["suite"] is None
    assert report["suites"] == []
    assert report["ruleset_version"] == RULESET_VERSION
    assert len({r["id"] for r in report["rules"]}) == len(report["rules"])
    injection = next(r for r in report["rules"] if r["id"] == "untrusted-content")
    assert "not yet measured" in injection["coverage"]
    assert all(
        h["source"] and h["evidence"] and h["before"] and h["after"]
        for h in report["history"]
    )
    # Callers cannot mutate the canonical rule definitions through a response.
    report["rules"][0]["name"] = "Changed outside the catalogue"
    assert assurance_report(store)["rules"][0]["name"] != report["rules"][0]["name"]


@pytest.mark.asyncio
async def test_suite_exercises_actual_controls_and_keeps_business_history_clean(
    store, monkeypatch
):
    from flowpilot import classifier, models

    def forbidden(*args, **kwargs):
        raise AssertionError("An assurance suite must not invoke a real AI route")

    monkeypatch.setattr(models.ModelRouter, "__init__", forbidden)
    monkeypatch.setattr(classifier, "classify", forbidden)
    result = await run_guardrail_suite(store)
    assert result["total"] >= 23
    assert result["passed"] == result["total"]
    assert result["failed"] == 0
    assert result["positive_controls"] >= 3
    assert result["negative_tests"] >= 10
    assert result["mode"] == "deterministic"
    assert len(result["implementation_digest"]) == 64
    assert result["application_revision"]
    assert result["rules_snapshot"]
    assert store.list("run") == []
    assert store.list("evaluation") == []
    assert store.get("guardrail_suite", result["id"]) == result
    assert not result["coverage"]["untrusted-content"]["tested"]
    assert result["coverage"]["legal-hold"]["passed"] == 1
    assert result["coverage"]["departmental-handoff"]["passed"] == 5
    assert "approval_token" not in json.dumps(result)
    assert all(r["expected"] == r["actual"] for r in result["results"])


@pytest.mark.asyncio
async def test_new_measurement_preserves_previous_result_and_versions(store):
    first = await run_guardrail_suite(store)
    frozen = copy.deepcopy(first)
    second = await run_guardrail_suite(store)
    assert first["id"] != second["id"]
    assert store.get("guardrail_suite", first["id"]) == frozen
    report = assurance_report(store)
    assert report["suite"]["id"] == second["id"]
    assert len(report["suites"]) == 2
    assert all(s["ruleset_version"] == RULESET_VERSION for s in report["suites"])


@pytest.mark.asyncio
async def test_suite_detects_broken_runtime_restrictions_instead_of_replaying_passes(
    store, monkeypatch
):
    import flowpilot.engine

    # Remove the enforcement boundary. The suite must measure a failure rather
    # than return its previous expected status or a stored successful response.
    monkeypatch.setattr(flowpilot.engine, "data_action_guard", lambda *args: None)
    result = await run_guardrail_suite(store)
    assert result["failed"] >= 2
    by_id = {r["id"]: r for r in result["results"]}
    assert not by_id["approved-legal-hold"]["passed"]
    assert not by_id["approved-retention"]["passed"]
    assert result["coverage"]["legal-hold"]["failed"] == 1


@pytest.mark.asyncio
async def test_suite_detects_missing_departmental_handoff(store, monkeypatch):
    import flowpilot.engine

    monkeypatch.setattr(flowpilot.engine, "create_reviews", lambda run: False)
    result = await run_guardrail_suite(store)
    by_id = {r["id"]: r for r in result["results"]}
    assert not by_id["privacy-only-handoff"]["passed"]
    assert not by_id["department-required"]["passed"]
    assert result["coverage"]["departmental-handoff"]["failed"] >= 2
