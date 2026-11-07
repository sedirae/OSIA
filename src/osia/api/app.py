from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import pathlib
from typing import Optional

import asyncpg
from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..backup import BackupError
from ..engine import Engine
from ..exchange import ArchiveError, CryptoError, ImportConflictError
from ..exchange.service import ExchangeService
from ..ids import new_id
from ..models import (
    ApiError,
    BackupCreateRequest,
    CreateBranchRequest,
    CreateInvestigationRequest,
    DecisionRequest,
    ExportRequest,
    ImportApplyRequest,
    ImportPreviewRequest,
    MatchProposalRequest,
    PolicyDeny,
    StopRequest,
)


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

    @app.exception_handler(ArchiveError)
    async def archive_error_handler(request: Request, exc: ArchiveError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "archive_invalid", "message": str(exc)}})

    @app.exception_handler(CryptoError)
    async def crypto_error_handler(request: Request, exc: CryptoError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "crypto_error", "message": str(exc)}})

    @app.exception_handler(ImportConflictError)
    async def import_conflict_handler(request: Request, exc: ImportConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "import_conflict", "message": str(exc), "details": {"conflicts": exc.conflicts}}},
        )

    @app.exception_handler(BackupError)
    async def backup_error_handler(request: Request, exc: BackupError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "backup_error", "message": str(exc)}})

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

    @app.get("/api/v1/investigations/{investigation_id}/graph")
    async def get_graph(
        investigation_id: str,
        request: Request,
        branch_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        entities = await engine.graph.list_entities(investigation_id, limit=limit, offset=offset)
        relations = await engine.graph.list_relations(investigation_id, branch_id=branch_id)
        return {
            "entities": [_entity_json(e) for e in entities],
            "relations": [_relation_json(r) for r in relations],
        }

    @app.get("/api/v1/investigations/{investigation_id}/entities/{entity_id}")
    async def get_entity(investigation_id: str, entity_id: str, request: Request) -> dict:
        await require_auth(request)
        sheet = await engine.graph.entity_sheet(investigation_id, entity_id)
        if sheet is None:
            raise ApiError("not_found", "entite inconnue", 404)
        return {
            "entity": _entity_json(sheet["entity"]),
            "identifiers": sheet["identifiers"],
            "relations_out": [_relation_json(r) for r in sheet["relations_out"]],
            "relations_in": [_relation_json(r) for r in sheet["relations_in"]],
            "branches": sheet["branches"],
        }

    @app.get("/api/v1/investigations/{investigation_id}/relations")
    async def list_relations(investigation_id: str, request: Request, branch_id: Optional[str] = None) -> list[dict]:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return [_relation_json(r) for r in await engine.graph.list_relations(investigation_id, branch_id=branch_id)]

    @app.get("/api/v1/investigations/{investigation_id}/assertions")
    async def list_assertions(
        investigation_id: str, request: Request, branch_id: Optional[str] = None, include_superseded: bool = False
    ) -> list[dict]:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return [_assertion_json(a) for a in await engine.graph.list_assertions(investigation_id, branch_id=branch_id, include_superseded=include_superseded)]

    @app.get("/api/v1/investigations/{investigation_id}/matches")
    async def list_matches(investigation_id: str, request: Request, status: Optional[str] = None) -> list[dict]:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return [_match_json(m) for m in await engine.graph.list_matches(investigation_id, status=status)]

    @app.post("/api/v1/investigations/{investigation_id}/matches", status_code=201)
    async def create_match(investigation_id: str, request: Request, body: MatchProposalRequest) -> dict:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        proposal = await engine.graph.propose_match(
            investigation_id,
            entity_a=body.entity_a,
            entity_b=body.entity_b,
            basis=body.basis,
            justification=body.justification,
            confidence=body.confidence,
        )
        return _match_json(proposal)

    @app.post("/api/v1/investigations/{investigation_id}/decisions", status_code=201)
    async def create_decision(
        investigation_id: str,
        request: Request,
        body: DecisionRequest,
        actor: Optional[str] = Header(default=None),
    ) -> dict:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        decision = await engine.graph.decide(
            investigation_id,
            target_type=body.target_type,
            target_id=body.target_id,
            action=body.action,
            payload=body.payload,
            reverts=body.reverts,
            actor=actor,
        )
        return _decision_json(decision)

    @app.get("/api/v1/investigations/{investigation_id}/decisions")
    async def list_decisions(investigation_id: str, request: Request) -> list[dict]:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return [_decision_json(d) for d in await engine.graph.list_decisions(investigation_id)]

    @app.get("/api/v1/investigations/{investigation_id}/etayage")
    async def get_etayage(investigation_id: str, request: Request, branch_id: Optional[str] = None) -> list[dict]:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return await engine.graph.etayage(investigation_id, branch_id=branch_id)

    @app.get("/api/v1/investigations/{investigation_id}/objectif")
    async def get_objectif(investigation_id: str, request: Request, branch_id: Optional[str] = None) -> dict:
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        return await engine.graph.objective_etaye(investigation_id, branch_id=branch_id)

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

    @app.post("/api/v1/investigations/{investigation_id}/export", status_code=201)
    async def export_investigation(
        investigation_id: str, request: Request, body: ExportRequest
    ) -> dict:
        """Export supervisé : archive .osia, rapport HTML autonome, ou les deux (D5, T7.4/T7.5).

        La phrase de chiffrement n'est jamais journalisée (OSIA-I-12)."""
        await require_auth(request)
        await _require_investigation(engine, investigation_id)
        result = await engine.exchange.export_investigation(
            investigation_id,
            format=body.format,
            branch_ids=body.branch_ids,
            include_proofs=body.include_proofs,
            exclusions=set(body.exclusions),
            encrypt=body.encrypt,
            passphrase=body.passphrase,
        )
        return _export_json(result)

    @app.get("/api/v1/exports")
    async def list_exports(request: Request) -> list[dict]:
        await require_auth(request)
        return [_export_row_json(r) for r in await engine.exchange.list_exports()]

    @app.get("/api/v1/exports/{export_id}")
    async def get_export(export_id: str, request: Request) -> dict:
        await require_auth(request)
        row = await engine.exchange.get_export(export_id)
        if row is None:
            raise ApiError("not_found", "export inconnu", 404)
        return _export_row_json(row)

    @app.get("/api/v1/exports/{export_id}/download")
    async def download_export(export_id: str, request: Request, file: str = "archive.osia"):
        await require_auth(request)
        row = await engine.exchange.get_export(export_id)
        if row is None:
            raise ApiError("not_found", "export inconnu", 404)
        allowed = {f["file"] for f in _loads(row["files"]) if isinstance(f, dict)}
        if file not in allowed:
            raise ApiError("not_found", f"fichier non présent dans cet export: {file}", 404)
        path = engine.settings.paths.data_dir / "exports" / export_id / file
        if not path.exists():
            raise ApiError("not_found", "fichier absent sur le serveur", 404)
        return FileResponse(path, filename=file)

    @app.post("/api/v1/import/preview")
    async def import_preview(request: Request):
        """Prévisualisation d'une archive .osia (T7.6) : JSON {path, passphrase} ou upload
        binaire (application/octet-stream). Aucune modification locale."""
        await require_auth(request)
        raw = await request.body()
        ct = request.headers.get("content-type", "")
        if ct.startswith("application/json") and raw:
            body = ImportPreviewRequest(**json.loads(raw))
            return await engine.exchange.preview_import(pathlib.Path(body.path), body.passphrase)
        tmp = engine.settings.paths.incoming_dir / f"upload_{new_id('up')}.osia"
        tmp.write_bytes(raw)
        try:
            return await engine.exchange.preview_import(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    @app.post("/api/v1/import/apply", status_code=201)
    async def import_apply(request: Request):
        """Application supervisée d'un import (T7.6, D5.7.2) : transaction unique, conflits
        explicites, aucune reprise de recherche ni appel IA. Accepte un corps JSON {path, mode,
        on_conflict, passphrase} ou un upload binaire application/octet-stream (client web ;
        mode/on_conflict/passphrase en query params)."""
        await require_auth(request)
        ct = request.headers.get("content-type", "")
        if ct.startswith("application/octet-stream"):
            raw = await request.body()
            tmp = engine.settings.paths.incoming_dir / f"upload_{new_id('up')}.osia"
            tmp.write_bytes(raw)
            try:
                return await engine.exchange.apply_import(
                    tmp,
                    mode=request.query_params.get("mode", "add"),
                    on_conflict=request.query_params.get("on_conflict", "fail"),
                    passphrase=request.query_params.get("passphrase") or None,
                )
            finally:
                tmp.unlink(missing_ok=True)
        raw = await request.body()
        if not raw:
            raise ApiError("bad_request", "corps JSON ou upload binaire requis", 400)
        try:
            body = ImportApplyRequest(**json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ApiError("bad_request", f"corps JSON invalide : {exc}", 400) from exc
        return await engine.exchange.apply_import(
            pathlib.Path(body.path), mode=body.mode, on_conflict=body.on_conflict, passphrase=body.passphrase
        )

    @app.post("/api/v1/backups", status_code=201)
    async def create_backup(request: Request, body: BackupCreateRequest) -> dict:
        """Sauvegarde technique manuelle à chaud (T2.6, CON-16) : base + preuves + manifeste."""
        await require_auth(request)
        result = await engine.backup.create(dest_dir=pathlib.Path(body.dest_dir) if body.dest_dir else None)
        return result

    @app.get("/api/v1/backups")
    async def list_backups(request: Request) -> list[dict]:
        await require_auth(request)
        return [_backup_json(r) for r in await engine.backup.list_backups()]

    @app.get("/api/v1/backups/{backup_id}")
    async def get_backup(backup_id: str, request: Request) -> dict:
        await require_auth(request)
        row = await engine.backup.get_backup(backup_id)
        if row is None:
            raise ApiError("not_found", "sauvegarde inconnue", 404)
        return _backup_json(row)

    @app.post("/api/v1/backups/{backup_id}/verify")
    async def verify_backup(backup_id: str, request: Request) -> dict:
        await require_auth(request)
        return await engine.backup.verify(backup_id)

    web_dir = (pathlib.Path(__file__).resolve().parent.parent / "web").resolve()

    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        """Interface web (lot C, CON-17) servie par le moteur ; protégée comme l'API en mode
        serveur même avec frontend (T5.7, EXEC-05)."""
        await require_auth(request)
        return FileResponse(web_dir / "index.html", media_type="text/html; charset=utf-8")

    @app.get("/static/{file_path:path}", include_in_schema=False)
    async def static_asset(file_path: str, request: Request):
        await require_auth(request)
        candidate = (web_dir / file_path).resolve()
        if candidate != web_dir and web_dir not in candidate.parents:
            raise ApiError("not_found", "fichier inconnu", 404)
        if not candidate.is_file():
            raise ApiError("not_found", "fichier inconnu", 404)
        media = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
        }.get(candidate.suffix.lower(), "application/octet-stream")
        return FileResponse(candidate, media_type=media)

    return app


async def _require_investigation(engine: Engine, investigation_id: str) -> None:
    if await engine.repo.get_investigation(investigation_id) is None:
        raise ApiError("not_found", "investigation inconnue", 404)


def _loads(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _entity_json(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "data": _loads(row["data"]),
        "merged_into": row["merged_into"],
        "created_at": row["created_at"].isoformat(),
    }


def _relation_json(row) -> dict:
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "src_id": row["src_id"],
        "dst_id": row["dst_id"],
        "type": row["type"],
        "direction": row["direction"],
        "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
        "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
        "support_level": row["support_level"],
        "human_decision": row["human_decision"],
        "proof_ids": _loads(row["proof_ids"]),
        "match_proposal_id": row["match_proposal_id"],
        "data": _loads(row["data"]),
    }


def _assertion_json(row) -> dict:
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "statement": row["statement"],
        "nature": row["nature"],
        "support_level": row["support_level"],
        "human_decision": row["human_decision"],
        "decisive": row["decisive"],
        "confidence": _loads(row["confidence"]),
        "proof_ids": _loads(row["proof_ids"]),
        "contradicted_by": _loads(row["contradicted_by"]),
        "superseded_by": row["superseded_by"],
        "created_at": row["created_at"].isoformat(),
    }


def _match_json(row) -> dict:
    return {
        "id": row["id"],
        "entity_a": row["entity_a"],
        "entity_b": row["entity_b"],
        "basis": row["basis"],
        "justification": row["justification"],
        "confidence": row["confidence"],
        "status": row["status"],
        "decided_by": row["decided_by"],
        "created_at": row["created_at"].isoformat(),
    }


def _decision_json(row) -> dict:
    return {
        "id": row["id"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "action": row["action"],
        "payload": _loads(row["payload"]),
        "reverts": row["reverts"],
        "created_at": row["created_at"].isoformat(),
    }


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


def _export_json(result: dict) -> dict:
    return {
        "export_id": result["export_id"],
        "format": result["format"],
        "encrypted": result["encrypted"],
        "partial": result["partial"],
        "counts": result["counts"],
        "warnings": result["warnings"],
        "files": result["files"],
    }


def _export_row_json(row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "format": row["format"],
        "investigation_ids": _loads(row["investigation_ids"]),
        "branch_ids": _loads(row["branch_ids"]),
        "exclusions": _loads(row["exclusions"]),
        "include_proofs": row["include_proofs"],
        "encrypted": row["encrypted"],
        "partial": row["partial"],
        "manifest_sha256": row["manifest_sha256"],
        "counts": _loads(row["counts"]),
        "warnings": _loads(row["warnings"]),
        "files": _loads(row["files"]),
    }


def _backup_json(row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "kind": row["kind"],
        "dest_dir": row["dest_dir"],
        "manifest_sha256": row["manifest_sha256"],
        "db_dump_sha256": row["db_dump_sha256"],
        "schema_version": row["schema_version"],
        "proof_files_count": row["proof_files_count"],
        "size_bytes": row["size_bytes"],
        "verified_at": row["verified_at"].isoformat() if row["verified_at"] else None,
        "verify_errors": _loads(row["verify_errors"]),
    }
