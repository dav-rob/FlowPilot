"""Local-only FastAPI application and browser API."""

from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ConfigDict
from .catalog import ROOT, WORKFLOWS, case_list, get_case
from .store import Store
from .engine import Engine, public_run
from .evaluation import Evaluator
from .registry import catalogue
from flowpilot_data.tools import open_session


class NewRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str | None = None
    partition: Literal["train", "validation", "test"] = "train"
    document: str | None = Field(default=None, max_length=50000)
    mode: Literal["simulation", "live"] = "simulation"
    purpose: Literal["business", "test"] = "business"
    title: str | None = Field(default=None, max_length=160)


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


class NewEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    partition: Literal["train", "validation", "test"] = "train"
    limit: int = Field(default=5, ge=1, le=25)
    mode: Literal["simulation", "live"] = "simulation"


def create_app(root=ROOT, state_dir=None):
    root = Path(root)
    store = Store(
        Path(state_dir or os.getenv("FLOWPILOT_STATE_DIR", root / ".runtime"))
        / "flowpilot.sqlite3"
    )
    engine = Engine(store, root=root)
    evaluator = Evaluator(store, engine)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        tasks = list(evaluator.tasks.values()) + list(engine.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        store.close()

    app = FastAPI(title="FlowPilot", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.engine = engine
    app.state.evaluator = evaluator
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                    return JSONResponse(
                        {
                            "detail": "Only the local FlowPilot interface can submit actions."
                        },
                        status_code=403,
                    )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-site action rejected."}, status_code=403
                )
            if (
                request.headers.get("content-length")
                and int(request.headers["content-length"]) > 100000
            ):
                return JSONResponse(
                    {"detail": "Request is too large."}, status_code=413
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "name": "FlowPilot"}

    @app.get("/api/config")
    async def config():
        from .models import ModelRouter

        try:
            models = ModelRouter().describe()
        except Exception as e:
            models = {"error": str(e)[:300]}
        key = bool(os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY"))
        from dataclasses import asdict

        return {
            "workflows": WORKFLOWS,
            "modes": [
                {
                    "id": "simulation",
                    "name": "Simulation",
                    "description": "Deterministic evidence policy. No AI calls or fabricated JEV responses.",
                },
                {
                    "id": "live",
                    "name": "Live AI",
                    "description": "Real local subscription models select tools. JEV classifies when an API key is configured.",
                },
            ],
            "classifier": {
                "mode": "jev" if key else "cli",
                "configured": key,
                "note": "Without JEV credentials live mode uses the configured CLI screening route. Simulation is always heuristic.",
            },
            "models": models,
            "limits": asdict(engine.limits),
        }

    @app.get("/api/cases")
    async def cases(partition: Literal["train", "validation", "test"] = "train"):
        rows = case_list(partition, root)
        return {"cases": rows, "total": len(rows)}

    @app.get("/api/cases/{case_id}")
    async def case(
        case_id: str, partition: Literal["train", "validation", "test"] = "train"
    ):
        c = get_case(case_id, partition, root)
        if not c:
            raise HTTPException(404, "Case not found")
        return c

    @app.get("/api/registry")
    async def registry():
        c = case_list("train", root)[0]
        return {"tools": catalogue(open_session(root / "data", "train", c["case_id"]))}

    @app.get("/api/runs")
    async def runs():
        return {
            "runs": [
                {k: v for k, v in public_run(r).items() if k not in ("events", "input")}
                for r in store.list("run")
            ]
        }

    @app.post("/api/runs", status_code=202)
    async def launch(body: NewRun):
        if len(engine.tasks) >= 3:
            raise HTTPException(
                429,
                "Three investigations are already active. Wait for one to complete.",
            )
        c = get_case(body.case_id, body.partition, root) if body.case_id else None
        if body.case_id and not c:
            raise HTTPException(404, "Case not found in this partition")
        document = (
            body.document if body.document is not None else c["document"] if c else None
        )
        if not document or not document.strip():
            raise HTTPException(422, "Select a case or paste a document")
        # A custom input receives a fresh case ID in an ephemeral public environment. No real case outage or scope metadata is borrowed.
        if not c:
            session_case_id = "CUSTOM-" + os.urandom(6).hex().upper()
        else:
            session_case_id = c["case_id"]
        try:
            r = engine.create(
                case_id=c["case_id"] if c else session_case_id,
                partition=body.partition,
                document=document,
                mode=body.mode,
                title=body.title or (c["title"] if c else "New incoming document"),
                session_case_id=session_case_id,
                purpose=body.purpose,
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return engine.start(r)

    def require_run(rid):
        r = store.get("run", rid)
        if not r:
            raise HTTPException(404, "Run not found")
        return r

    @app.get("/api/runs/{rid}")
    async def run(rid: str):
        return public_run(require_run(rid))

    @app.post("/api/runs/{rid}/cancel")
    async def cancel(rid: str):
        require_run(rid)
        return await engine.cancel(rid)

    @app.post("/api/runs/{rid}/replay", status_code=201)
    async def replay(rid: str):
        require_run(rid)
        try:
            return engine.replay(rid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/runs/{rid}/approvals/{request_id}")
    async def approval(rid: str, request_id: str, body: Approval):
        require_run(rid)
        try:
            return await engine.approve(rid, request_id, body.approve)
        except KeyError as e:
            raise HTTPException(404, "Approval request not found") from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/evaluations")
    async def evaluations():
        return {"evaluations": store.list("evaluation")[:50]}

    @app.post("/api/evaluations", status_code=202)
    async def evaluate(body: NewEvaluation):
        if evaluator.tasks:
            raise HTTPException(409, "An evaluation is already running")
        return evaluator.create(body.partition, body.limit, body.mode)

    @app.get("/api/evaluations/{eid}")
    async def evaluation(eid: str):
        obj = store.get("evaluation", eid)
        if not obj:
            raise HTTPException(404, "Evaluation not found")
        return obj

    dist = root / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        if (dist / "index.html").is_file():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {
                "message": "Build the frontend with npm --prefix frontend install && npm --prefix frontend run build.",
                "api": "/docs",
            }
        )

    return app
