import time
import pytest
from fastapi.testclient import TestClient
from flowpilot.api import create_app
from flowpilot.catalog import ROOT


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(ROOT, tmp_path)) as c:
        yield c


def wait_run(client, rid):
    for _ in range(150):
        r = client.get("/api/runs/" + rid).json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.03)
    pytest.fail("Run did not finish")


def test_api_investigation_and_governance(client):
    assert client.get("/api/health").json()["status"] == "ok"
    cases = client.get("/api/cases").json()["cases"]
    assert len(cases) == 150 and sum(c["showcase"] for c in cases) == 5
    assert len(client.get("/api/registry").json()["tools"]) >= 60
    r = client.post(
        "/api/runs", json={"case_id": "IN-B148DF6144", "mode": "simulation"}
    )
    assert r.status_code == 202
    run = wait_run(client, r.json()["id"])
    assert run["status"] == "awaiting_approval", run.get("error")
    assert run["classification"]["primary"] == "supplier_fraud"
    assert run["outcome"]["risk"] == "critical"
    assert not any(k.startswith("_") for k in run)
    p = run["approvals"][0]
    url = f"/api/runs/{run['id']}/approvals/{p['request_id']}"
    approved = client.post(url, json={"approve": True})
    assert approved.status_code == 200, approved.text
    assert approved.json()["approvals"][0]["status"] == "executed"
    assert client.post(url, json={"approve": True}).status_code == 409
    replay = client.post(f"/api/runs/{run['id']}/replay").json()
    assert replay["mode"] == "replay"
    assert (
        client.post(
            f"/api/runs/{replay['id']}/approvals/{p['request_id']}",
            json={"approve": True},
        ).status_code
        == 409
    )


def test_invalid_requests_and_cross_site_changes(client):
    assert client.post("/api/runs", json={"document": ""}).status_code == 422
    assert (
        client.post(
            "/api/runs", json={"case_id": "../../evaluation", "mode": "simulation"}
        ).status_code
        == 404
    )
    assert client.get("/api/cases?partition=../../evaluation").status_code == 422
    assert (
        client.post(
            "/api/runs", json={"document": "x", "mode": "pretend-live"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/runs",
            json={"document": "x"},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert client.get("/api/runs/not-found").status_code == 404
    assert client.get("/api/no-such-route").status_code == 404


def test_custom_document_and_evaluation(client):
    r = client.post(
        "/api/runs",
        json={"document": "Please process invoice SI-79253.", "mode": "simulation"},
    ).json()
    run = wait_run(client, r["id"])
    assert run["case_id"].startswith("CUSTOM-")
    assert run["status"] in ("completed", "awaiting_approval"), run.get("error")
    r = client.post(
        "/api/evaluations",
        json={"partition": "train", "limit": 5, "mode": "simulation"},
    )
    assert r.status_code == 202
    for _ in range(250):
        e = client.get("/api/evaluations/" + r.json()["id"]).json()
        if e["status"] not in ("queued", "running"):
            break
        time.sleep(0.03)
    assert e["status"] == "completed", e.get("error")
    assert e["completed"] == 5
    assert e["metrics"]["runtime"]["model_calls"] == 0
    assert "Deterministic" in e["warning"]
    assert all("expected" not in row for row in e["results"])
