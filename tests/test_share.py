import httpx
import pytest
from fastapi.testclient import TestClient
from flowpilot.share import create_share_app

PUBLIC = "https://console.example.test:8443/flowpilot/"
ORIGIN = "https://console.example.test:8443"


@pytest.fixture
def gateway():
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(
            200, json={"path": request.url.path, "query": request.url.query.decode()}
        )

    app = create_share_app(PUBLIC, transport=httpx.MockTransport(upstream))
    with TestClient(app, base_url=PUBLIC) as client:
        yield client, calls


def test_demo_pages_and_actions_open_without_a_login(gateway):
    client, calls = gateway
    for method, path in [("GET", ""), ("GET", "api/runs"), ("POST", "api/runs")]:
        response = client.request(method, path)
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers
        assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 3


def test_public_paths_and_browser_actions_reach_only_local_backend(gateway):
    client, calls = gateway
    assert client.get("assets/app.js").json()["path"] == "/assets/app.js"
    response = client.post(
        "api/runs?example=1",
        json={"mode": "simulation"},
        headers={
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "same-origin",
            "Cookie": "private=value",
            "Authorization": "Basic unused-browser-credentials",
            "X-Forwarded-Host": "attacker.example",
        },
    )
    assert response.status_code == 200
    request = calls[-1]
    assert str(request.url) == "http://127.0.0.1:8766/api/runs?example=1"
    assert request.headers["origin"] == "http://127.0.0.1:8766"
    for key in ("authorization", "cookie", "x-forwarded-host"):
        assert key not in request.headers
    assert request.content == b'{"mode":"simulation"}'
    # Same handler also works when Tailscale has already stripped /flowpilot/.
    assert client.get(ORIGIN + "/api/health").json()["path"] == "/api/health"


def test_cross_site_writes_and_host_spoofing_are_rejected(
    gateway,
):
    client, calls = gateway
    for headers in [
        {"Origin": "https://attacker.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ]:
        assert client.post("api/runs", headers=headers).status_code == 403
    assert client.get("api/runs", headers={"Host": "localhost"}).status_code == 400
    assert calls == []


def test_request_limit_is_enforced_before_forwarding(gateway):
    client, calls = gateway
    assert client.post("api/runs", content=b"x" * 100001).status_code == 413
    assert calls == []


def test_unavailable_backend_does_not_expose_internal_errors():
    def unavailable(request):
        raise httpx.ConnectError("private internal details", request=request)

    app = create_share_app(PUBLIC, transport=httpx.MockTransport(unavailable))
    with TestClient(app, base_url=PUBLIC) as client:
        response = client.get("api/health")
        assert response.status_code == 502
        assert "private internal details" not in response.text


def test_share_requires_a_valid_https_url():
    with pytest.raises(ValueError):
        create_share_app("http://example.test/")


def test_shared_html_resolves_assets_and_api_under_its_prefix():
    def html(request):
        return httpx.Response(
            200,
            text='<html><head><script src="./assets/app.js"></script></head></html>',
            headers={"Content-Type": "text/html"},
        )

    app = create_share_app(PUBLIC, transport=httpx.MockTransport(html))
    with TestClient(app, base_url=PUBLIC) as client:
        response = client.get("")
        assert '<base href="/flowpilot/">' in response.text
        assert 'src="./assets/app.js"' in response.text
