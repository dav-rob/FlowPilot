"""Loopback gateway for an explicitly configured public HTTPS demo share.

The investigation server stays local-only. This process forwards demo
requests to that one server; it never opens another engine or database.
"""

from __future__ import annotations

import argparse
from html import escape
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

UPSTREAM = "http://127.0.0.1:8766"
MAX_BODY = 100000


def create_share_app(public_url: str, *, transport=None):
    parsed = urlsplit(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/")
        or ".." in parsed.path.split("/")
    ):
        raise ValueError("Share URL must be an HTTPS address ending in /.")
    origin = f"https://{parsed.netloc}"
    prefix = parsed.path.rstrip("/")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            transport=transport, timeout=120, follow_redirects=False, trust_env=False
        ) as client:
            app.state.client = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "OPTIONS"])
    async def proxy(request: Request, path: str):
        # Validate the incoming origin before replacing it for the local server.
        if request.headers.get("host", "").lower() != parsed.netloc.lower():
            raise HTTPException(400, "Unexpected share address.")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") not in (None, origin):
                raise HTTPException(403, "Cross-site action rejected.")
            if request.headers.get("sec-fetch-site") == "cross-site":
                raise HTTPException(403, "Cross-site action rejected.")
        # Tailscale removes the handler prefix; accept it intact for direct tests too.
        if prefix and request.url.path == prefix:
            return RedirectResponse(public_url, status_code=307)
        if prefix and request.url.path.startswith(prefix + "/"):
            path = request.url.path[len(prefix) + 1 :]
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise HTTPException(413, "Request is too large.")
        headers = {
            key: request.headers[key]
            for key in ("accept", "content-type", "if-none-match", "if-modified-since")
            if key in request.headers
        }
        if request.headers.get("origin"):
            headers["origin"] = UPSTREAM
        # Do not forward authentication, identity, cookies or proxy headers.
        url = UPSTREAM + "/" + quote(path.lstrip("/"), safe="/@:")
        if request.url.query:
            url += "?" + request.url.query
        try:
            upstream = await request.app.state.client.request(
                request.method, url, content=bytes(body), headers=headers
            )
        except httpx.HTTPError:
            raise HTTPException(
                502, "The local FlowPilot service is unavailable."
            ) from None
        response_headers = {
            key: upstream.headers[key]
            for key in ("content-type", "etag", "last-modified", "content-disposition")
            if key in upstream.headers
        }
        if "location" in upstream.headers:
            location = upstream.headers["location"]
            if location.startswith(UPSTREAM + "/"):
                location = public_url + location[len(UPSTREAM) + 1 :]
            elif location.startswith("/"):
                location = public_url + location.lstrip("/")
            response_headers["location"] = location
        content = upstream.content
        if "text/html" in upstream.headers.get("content-type", ""):
            # Also resolve assets/API/hash links correctly when the share URL is
            # opened without its trailing slash (the proxy strips that prefix).
            base = f'<base href="{escape(parsed.path, quote=True)}">'.encode()
            content = content.replace(b"<head>", b"<head>" + base, 1)
        return Response(content, upstream.status_code, headers=response_headers)

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Run the public FlowPilot demo sharing gateway"
    )
    parser.add_argument("--config", type=Path, default=Path(".runtime/share.json"))
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise SystemExit("Share configuration must be private: chmod 600 <config>.")
    config = json.loads(args.config.read_text())
    app = create_share_app(config["url"])
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
