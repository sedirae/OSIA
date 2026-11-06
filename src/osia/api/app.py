from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Optional

import asyncpg
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..engine import Engine
from ..models import ApiError, CreateBranchRequest, CreateInvestigationRequest, PolicyDeny, StopRequest


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(
        title="OSIA",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    settings = engine.settings

    async def require_auth(request: Request) -> None:
        """Mode serveur : authentification obligatoire, même sans frontend (T5.7, EXEC-05)."""
        if settings.mode != "server":
            return
        expected = settings.auth_token_hash or await engine.repo.get_setting("auth_token_hash")
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        digest = hashlib.sha256(token.encode()).hexdigest() if token else ""
        if not expected or not hmac.compare_digest(digest, str(expected)):
            raise ApiError("unauthorized", "authentification requise en mode serveur (T5.7)", 401)

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(PolicyDeny)
    async def policy_error_handler(request: Request, exc: PolicyDeny) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": {"code": "policy_denied", "message": exc.reason, "scope": exc.scope}})

    @app.get("/api/v1/health")
    async def health(request: Request) -> dict:
        await require_auth(request)
        return {"status": "ok", "version": "0.1.0", "mode": settings.mode}

    @app.get("/api/v1/profiles")
    async def profiles(request: Request) -> list[dict]:
        await require_auth(request)
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "max_rebonds": p["max_rebonds"],
                "max_source_requests": p["max_source_requests"],
                "max_ai_calls": p["max_ai_calls"],
                "max_duration_seconds": p["max_duration_seconds"],
                "max_cost_cents": p["max_cost_cents"],
                "is_default": p["is_default"],
            }
            for p in await engine.repo.list_profiles()
        ]

    @app.post("/api/v1/investigations", status_code=201)
    async def create_investigation(
        request: Request,
        body: CreateInvestigationRequest,
        idempotency_key: Optional[str] = Header(default=None),
    ) -> JSONResponse:
        await require_auth(request)
        key = idempotency_key or body.idempotency_key
        if key:
            body.idempotency_key = key
            existing = await engine.repo.find_investigation_by_key(key)
            if existing is not None:
                if existing["title"] != body.title:
                    raise ApiError("idempotency_conflict", "clé d'idempotence déjà utilisée pour une autre ressource (V1.5)", 409)
                return JSONResponse(status_code=200, content=_inv_json(existing))
        try:
            inv = await engine.orchestrator.start_investigation(body)
        except asyncpg.UniqueViolationError:
            existing = await engine.repo.find_investigation_by_key(key)
            if existing is None:
                raise
            if existing["title"] != body.title:
                raise ApiError("idempotency_conflict", "clé d'idempotence déjà utilisée pour une autre ressource (V1.5)", 409)
            return JSONResponse(status_code=200, content=_inv_json(existing))
        return JSONResponse(status_code=201, content=_inv_json(inv))

    @app.get("/api/v1/investigations")
    async def list_investigations(request: Request) -> list[dict]:
        await require_auth(request)
        return [_inv_json(r) for r in await engine.repo.list_investigations()]

    @app.get("/api/v1/investigations/{investigation_id}")
    async def get_investigation(investigation_id: str, request: Request) -> dict:
        await require_auth(request)
        inv = await engine.repo.get_investigation(investigation_id)
        if inv is None:
            raise ApiError("not_found", "investigation inconnue", 404)
        return _inv_json(inv)

    @app.post("/api/v1/investigations/{investigation_id}/stop")
    async def stop_investigation(investigation_id: str, request: Request, body: StopRequest) -> dict:
        await require_auth(request)
        inv = await engine.orchestrator.stop(investigation_id, body.reason)
        if inv is None:
            raise ApiError("not_found", "investigation inconnue", 404)
        return _inv_json(inv)

    @app.post("/api/v1/investigations/{investigation_id}/resume")
    async def resume_investigation(investigation_id: str, request: Request) -> dict:
        await require_auth(request)
        inv = await engine.orchestrator.resume(investigation_id)
        return _inv_json(inv)

    @app.post("/api/v1/investigations/{investigation_id}/branches", status_code=201)
    async def create_branch(
        investigation_id: str,
        request: Request,
        body: CreateBranchRequest,
        idempotency_key: Optional[str] = Header(default=None),
    ) -> JSONResponse:
        await require_auth(request)
        if idempotency_key:
            body.idempotency_key = idempotency_key
        try:
            branch = await engine.orchestrator.create_branch(investigation_id, body)
        except asyncpg.UniqueViolationError:
            existing = await engine.repo.find_branch_by_key(idempotency_key or "")
            if existing is None:
                raise
            return JSONResponse(status_code=200, content=_branch_json(existing))
        return JSONResponse(status_code=201, content=_branch_json(branch))

    @app.get("/api/v1/investigations/{investigation_id}/branches")
    async def list_branches(investigation_id: str, request: Request) -> list[dict]:
        await require_auth(request)
        return [_branch_json(b) for b in await engine.repo.list_branches(investigation_id)]

    @app.get("/api/v1/investigations/{investigation_id}/tasks")
    async def list_tasks(investigation_id: str, request: Request) -> list[dict]:
        await require_auth(request)
        return [_task_json(t) for t in await engine.repo.list_tasks(investigation_id)]

    @app.get("/api/v1/investigations/{investigation_id}/budget")
    async def get_budget(investigation_id: str, request: Request) -> dict:
        await require_auth(request)
        view = await engine.budgets.budget_view(investigation_id)
        return view.model_dump()

    @app.get("/api/v1/investigations/{investigation_id}/proofs")
    async def list_proofs(investigation_id: str, request: Request) -> list[dict]:
        await require_auth(request)
        return [
            {
                "id": r["id"],
                "sha256": r["proof_sha256"],
                "source_url": r["source_url"],
                "media_type": r["media_type"],
                "label": r["label"],
                "fetched_at": r["fetched_at"].isoformat(),
                "size_bytes": r["size_bytes"],
            }
            for r in await engine.repo.list_proof_refs(investigation_id)
        ]

    @app.get("/api/v1/investigations/{investigation_id}/events", response_model=None)
    async def stream_events(investigation_id: str, request: Request, last_event_id: int = 0):
        await require_auth(request)
        if "text/event-stream" not in request.headers.get("accept", ""):
            events = await engine.repo.list_events(investigation_id, after_id=last_event_id)
            return [_event_json(e) for e in events]

        queue = engine.bus.subscribe(investigation_id)
        events = await engine.repo.list_events(investigation_id, after_id=last_event_id)

        async def stream():
            last_sent = last_event_id
            try:
                for event in events:
                    last_sent = max(last_sent, event.id)
                    yield _sse(event)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if event.investigation_id != investigation_id:
                        continue
                    if event.id <= last_sent:
                        continue
                    last_sent = event.id
                    yield _sse(event)
            finally:
                engine.bus.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _inv_json(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "objective": row["objective"],
        "hints": row["hints"] if isinstance(row["hints"], list) else json.loads(row["hints"]),
        "profile_id": row["profile_id"],
        "effective_limits": row["effective_limits"] if isinstance(row["effective_limits"], dict) else json.loads(row["effective_limits"]),
        "state": row["state"],
        "stop_reason": row["stop_reason"],
        "created_at": row["created_at"].isoformat(),
    }


def _branch_json(row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "parent_branch_id": row["parent_branch_id"],
        "objective": row["objective"],
        "effective_limits": row["effective_limits"] if isinstance(row["effective_limits"], dict) else json.loads(row["effective_limits"]),
        "state": row["state"],
        "stop_reason": row["stop_reason"],
        "depth": row["depth"],
    }


def _task_json(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "state": row["state"],
        "depth": row["depth"],
        "payload": row["payload"],
        "error": row["error"],
    }


def _event_json(event) -> dict:
    return {
        "id": event.id,
        "type": event.type,
        "investigation_id": event.investigation_id,
        "branch_id": event.branch_id,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def _sse(event) -> str:
    return f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(_event_json(event), ensure_ascii=False)}\n\n"
