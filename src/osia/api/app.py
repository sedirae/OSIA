from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import pathlib
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, Header, Request
from pydantic import ValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..backup import BackupError
from ..engine import Engine
from ..exchange import ArchiveError, CryptoError, ImportConflictError
from ..exchange.service import ExchangeService
from ..ids import new_id
from ..models import (
    AIFallbackRequest,
    AITestRequest,
    ApiError,
    BackupCreateRequest,
    CreateBranchRequest,
    CreateInvestigationRequest,
    DecisionRequest,
    ExportRequest,
    ConnectorToggleRequest,
    HealthCheckRequest,
    ImportApplyRequest,
    ImportPreviewRequest,
    LoginRequest,
    MatchProposalRequest,
    ProfileCreateRequest,
    SecretSetRequest,
    SettingsUpdateRequest,
    LimitSet,
    PolicyDeny,
    StopRequest,
    EDITABLE_SETTINGS,
    validate_setting_value,
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

    def _client(request: Request) -> str | None:
        return request.client.host if request.client else None

    async def require_auth(request: Request) -> None:
        """Mode serveur : authentification obligatoire, même sans frontend (T5.7, EXEC-05).

        Deux credentials acceptés : le jeton administrateur statique (hash comparé en constant
        time) ou un jeton de session `sess_*` valide, non expiré et non révoqué (CON-05).
        Tout refus est journalisé dans l'audit de sécurité (T5.9), sans jamais le secret."""
        if settings.mode != "server":
            return
        expected = settings.auth_token_hash or await engine.repo.get_setting("auth_token_hash")
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        if not expected:
            engine.audit.log("auth.denied", "failure", detail={"reason": "no_token_configured"}, client=_client(request))
            raise ApiError("unauthorized", "authentification requise en mode serveur (T5.7)", 401)
        digest = hashlib.sha256(token.encode()).hexdigest() if token else ""
        if hmac.compare_digest(digest, str(expected)):
            return
        if token.startswith("sess_") and await engine.sessions.validate(token):
            return
        engine.audit.log("auth.denied", "failure", detail={"reason": "bad_credentials"}, client=_client(request))
        raise ApiError("unauthorized", "authentification requise en mode serveur (T5.7)", 401)

    def _audit_op(action: str, request: Request, detail: dict | None = None) -> None:
        """Journalise une opération sensible dans l'audit de sécurité (T5.9), sans secrets."""
        engine.audit.log(action, "success", detail=detail, client=_client(request))

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

    @app.post("/api/v1/auth/login")
    async def login(request: Request, body: LoginRequest) -> dict:
        """CON-05 (T5.7) : en mode serveur, échange le jeton administrateur contre une session
        expirable et révocable. En mode desktop, aucune authentification n'est requise (local)."""
        if settings.mode != "server":
            raise ApiError("bad_request", "mode desktop : aucune authentification requise (liaison locale, T1)", 400)
        expected = settings.auth_token_hash or await engine.repo.get_setting("auth_token_hash")
        digest = hashlib.sha256(body.token.encode()).hexdigest() if body.token else ""
        if not expected or not hmac.compare_digest(digest, str(expected)):
            engine.audit.log("auth.login", "failure", client=_client(request))
            raise ApiError("unauthorized", "jeton administrateur invalide", 401)
        token, expires = await engine.sessions.create(client_info=_client(request))
        engine.audit.log("auth.login", "success", detail={"ttl_hours": settings.session_ttl_hours}, client=_client(request))
        return {"session_token": token, "expires_at": expires.isoformat(), "ttl_hours": settings.session_ttl_hours}

    @app.post("/api/v1/auth/logout")
    async def logout(request: Request) -> dict:
        """CON-05 : révoque la session présentée (le jeton statique admin reste valable)."""
        await require_auth(request)
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        revoked = False
        if token.startswith("sess_"):
            revoked = await engine.sessions.revoke(token)
        engine.audit.log("auth.logout", "success", detail={"session_revoked": revoked}, client=_client(request))
        return {"revoked": revoked}

    @app.get("/api/v1/auth/sessions")
    async def list_sessions(request: Request) -> list[dict]:
        """CON-05 : sessions actives (hash jamais exposé)."""
        await require_auth(request)
        return await engine.sessions.list_active()

    @app.get("/api/v1/profiles")
    async def profiles(request: Request) -> list[dict]:
        await require_auth(request)
        return [_profile_json(p) for p in await engine.repo.list_profiles()]

    @app.post("/api/v1/profiles", status_code=201)
    async def create_profile(request: Request, body: ProfileCreateRequest) -> dict:
        """CON-13 / D3 §5.3 : profil personnalisé enregistrable. Limites validées (LimitSet :
        rebonds 1–10, etc.) avant enregistrement (D7 §9.3) ; un seul profil par défaut. Audité."""
        await require_auth(request)
        try:
            limits = LimitSet(**body.limits)
        except ValidationError as exc:
            raise ApiError("bad_request", f"limites invalides : {exc.errors()}", 400) from exc
        try:
            row = await engine.repo.create_profile(
                profile_id=body.id,
                name=body.name,
                limits=limits.model_dump(),
                is_default=body.is_default,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("conflict", f"profil déjà existant : {body.id}", 409)
        _audit_op("op.profile.create", request, {"profile_id": body.id, "is_default": body.is_default})
        return _profile_json(row)

    @app.get("/api/v1/settings")
    async def get_settings(request: Request) -> dict:
        """CON-13 / D7 §9.1 : paramètres globaux effectifs (clés modifiables uniquement, sans secrets)."""
        await require_auth(request)
        return {"settings": {key: await engine.repo.get_setting(key) for key in EDITABLE_SETTINGS}}

    @app.put("/api/v1/settings")
    async def update_settings(request: Request, body: SettingsUpdateRequest) -> dict:
        """CON-13 / D7 §9.3 : modification des paramètres globaux, validée avant enregistrement,
        persistée et auditée. S'applique aux FUTURES opérations (D7 §9.2 : pas de rétroactivité —
        les investigations en cours conservent leurs effective_limits)."""
        await require_auth(request)
        updated: dict[str, Any] = {}
        for key, raw in body.settings.items():
            try:
                value = validate_setting_value(key, raw)
            except ValueError as exc:
                raise ApiError("bad_request", str(exc), 400) from exc
            await engine.repo.set_setting(key, value)
            updated[key] = value
        if "audit_retention_days" in updated:
            engine.audit.retention_days = int(updated["audit_retention_days"])
        if "session_ttl_hours" in updated:
            from datetime import timedelta

            engine.sessions.ttl = timedelta(hours=int(updated["session_ttl_hours"]))
        _audit_op("op.settings.update", request, {"keys": sorted(updated)})
        return {"updated": updated}

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
        _audit_op("op.export", request, {"investigation_id": investigation_id, "format": body.format, "encrypted": body.encrypt})
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
        _audit_op("op.export.download", request, {"export_id": export_id, "file": file})
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
                result = await engine.exchange.apply_import(
                    tmp,
                    mode=request.query_params.get("mode", "add"),
                    on_conflict=request.query_params.get("on_conflict", "fail"),
                    passphrase=request.query_params.get("passphrase") or None,
                )
            finally:
                tmp.unlink(missing_ok=True)
            _audit_op("op.import.apply", request, {"mode": request.query_params.get("mode", "add"), "upload": True})
            return result
        raw = await request.body()
        if not raw:
            raise ApiError("bad_request", "corps JSON ou upload binaire requis", 400)
        try:
            body = ImportApplyRequest(**json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ApiError("bad_request", f"corps JSON invalide : {exc}", 400) from exc
        result = await engine.exchange.apply_import(
            pathlib.Path(body.path), mode=body.mode, on_conflict=body.on_conflict, passphrase=body.passphrase
        )
        _audit_op("op.import.apply", request, {"mode": body.mode, "on_conflict": body.on_conflict})
        return result

    @app.post("/api/v1/backups", status_code=201)
    async def create_backup(request: Request, body: BackupCreateRequest) -> dict:
        """Sauvegarde technique manuelle à chaud (T2.6, CON-16) : base + preuves + manifeste."""
        await require_auth(request)
        result = await engine.backup.create(dest_dir=pathlib.Path(body.dest_dir) if body.dest_dir else None)
        _audit_op("op.backup.create", request, {"backup_id": result.get("id")})
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
        result = await engine.backup.verify(backup_id)
        _audit_op("op.backup.verify", request, {"backup_id": backup_id, "verified": result.get("verified")})
        return result

    @app.get("/api/v1/net/policy")
    async def get_net_policy(request: Request) -> dict:
        """CON-06 / T5.4 : politique réseau effective (domaines, limites)."""
        await require_auth(request)
        p = engine.netguard.policy
        return {
            "allowed_domains": sorted(p.allowed_domains),
            "denied_domains": sorted(p.denied_domains),
            "max_redirects": p.max_redirects,
            "timeout_seconds": p.timeout_seconds,
            "max_bytes": p.max_bytes,
            "min_interval_seconds": p.min_interval_seconds,
            "blocked_networks": [str(n) for n in p.blocked_networks],
        }

    @app.get("/api/v1/secrets")
    async def list_secrets(request: Request) -> dict:
        """CON-06 / T5.5 : noms des secrets uniquement, jamais les valeurs."""
        await require_auth(request)
        return {"names": engine.secrets.names()}

    @app.put("/api/v1/secrets/{name}")
    async def set_secret(name: str, request: Request, body: SecretSetRequest) -> dict:
        await require_auth(request)
        engine.secrets.set(name, body.value)
        _audit_op("op.secret.set", request, {"name": name})
        return {"name": name, "stored": True}

    @app.delete("/api/v1/secrets/{name}")
    async def delete_secret(name: str, request: Request) -> dict:
        await require_auth(request)
        deleted = engine.secrets.delete(name)
        _audit_op("op.secret.delete", request, {"name": name, "existed": deleted})
        return {"name": name, "deleted": deleted}

    @app.get("/api/v1/connectors")
    async def list_connectors(request: Request) -> list[dict]:
        """CON-06 / T5.1 : connecteurs enregistrés avec leur niveau de confiance."""
        await require_auth(request)
        return engine.registry.list()

    @app.post("/api/v1/connectors/{connector_id}/toggle")
    async def toggle_connector(connector_id: str, request: Request, body: ConnectorToggleRequest) -> dict:
        """CON-06 / T5.1 : activation/désactivation. Un connecteur EXPERIMENTAL exige
        `confirm: true` (autorisation explicite) ; l'autorisation est persistée et auditée."""
        await require_auth(request)
        manifest = None
        for entry in engine.registry.list():
            if entry["id"] == connector_id:
                manifest = entry
        if manifest is None:
            raise ApiError("not_found", "connecteur inconnu", 404)
        if body.enabled and manifest["trust_level"] == "experimental" and not body.confirm:
            raise ApiError("confirmation_requise", "connecteur expérimental : confirm=true exigé (T5.1)", 400)
        engine.registry.set_enabled(connector_id, body.enabled)
        if body.enabled and manifest["trust_level"] == "experimental":
            await engine.repo.set_setting(f"allow_experimental:{connector_id}", True)
            engine.policy.allow_target(connector_id)
        elif not body.enabled:
            await engine.repo.set_setting(f"allow_experimental:{connector_id}", False)
        _audit_op("op.connector.toggle", request, {"connector_id": connector_id, "enabled": body.enabled, "trust_level": manifest["trust_level"]})
        return {"id": connector_id, "enabled": body.enabled}

    @app.get("/api/v1/connectors/{connector_id}/health")
    async def connector_health(connector_id: str, request: Request) -> dict:
        """CON-07/CON-08 / B7 §9.1 : dernier état de surveillance connu d'un connecteur
        (operationnel | degrade | suspendu | obsolete | inconnu). V1 : contrôles manuels."""
        await require_auth(request)
        known = {e["id"] for e in engine.registry.list()}
        if connector_id not in known:
            raise ApiError("not_found", "connecteur inconnu", 404)
        report = engine.health.last_report(connector_id)
        if report is None:
            return {
                "connector_id": connector_id,
                "state": "inconnu",
                "checked_at": None,
                "detail": "aucun contrôle effectué (V1 : contrôles manuels via POST /api/v1/connectors/health-check)",
                "http_status": None,
                "validation_problems": [],
                "probe_url": None,
            }
        return _health_json(report)

    @app.post("/api/v1/connectors/health-check")
    async def health_check(request: Request, body: HealthCheckRequest) -> dict:
        """CON-07/CON-08 / B7 §9.1 : contrôle manuel de santé (sonde légère + validation
        sémantique de la réponse). Audité (T5.9). Aucun sondage planifié en V1 (B7 §9.5)."""
        await require_auth(request)
        if body.connector_id:
            reports = [await engine.health.check(body.connector_id, body.probe_query)]
        else:
            reports = await engine.health.check_all(body.probe_query)
        _audit_op(
            "op.connector.health_check",
            request,
            {"connector_id": body.connector_id, "states": {r.connector_id: r.state.value for r in reports}},
        )
        return {"reports": [_health_json(r) for r in reports]}

    @app.get("/api/v1/ai/providers")
    async def ai_providers(request: Request) -> dict:
        """CON-11 / D2 §4.2 : fournisseurs IA enregistrés, modèles par rôle, replis autorisés.
        Aucune clé API n'est exposée (T8.8, D2 §4.3)."""
        await require_auth(request)
        roles_by_key: dict[str, list[str]] = {}
        for role, key in engine.broker.role_models.items():
            roles_by_key.setdefault(key, []).append(role)
        providers = [
            {
                "key": key,
                "provider": ad.provider,
                "model": ad.model,
                "paid": ad.paid,
                "cost_per_call_cents": ad.cost_per_call_cents,
                "roles": roles_by_key.get(key, []),
                "fallback_to": engine.broker.allowed_fallbacks.get(key),
            }
            for key, ad in engine.broker.adapters.items()
        ]
        return {
            "providers": providers,
            "fallback_local_to_cloud_authorized": bool(engine.broker.allowed_fallbacks.get("local")),
        }

    @app.post("/api/v1/ai/fallback")
    async def ai_fallback(request: Request, body: AIFallbackRequest) -> dict:
        """CON-11 / T8.8/T8.9 + V1.3 + D2 §4.4 : autorise ou révoque le repli local -> cloud
        (autorisation de transmission persistée). Sans cette autorisation, aucun repli n'est
        possible ; avec, le repli payant reste soumis à la réservation budgétaire (T8.4)."""
        await require_auth(request)
        await engine.repo.set_setting("allow_ai_fallback_local_to_cloud", body.enabled)
        if body.enabled and "local" in engine.broker.adapters and "mistral" in engine.broker.adapters:
            engine.broker.allowed_fallbacks["local"] = "mistral"
        else:
            engine.broker.allowed_fallbacks.pop("local", None)
        _audit_op("op.ai.fallback.toggle", request, {"enabled": body.enabled})
        return {"allow_ai_fallback_local_to_cloud": body.enabled, "fallbacks": dict(engine.broker.allowed_fallbacks)}

    @app.post("/api/v1/ai/test")
    async def ai_test(request: Request, body: AITestRequest) -> dict:
        """CON-11 / D2 §4.2 : test de connexion explicite d'un fournisseur (GET /models, non
        facturé). Aucun appel payant n'est lancé ici (B6) ; la clé n'est jamais journalisée."""
        await require_auth(request)
        adapter = engine.broker.adapters.get(body.provider_key)
        if adapter is None:
            raise ApiError("not_found", "fournisseur inconnu", 404)
        try:
            result = await adapter.ping()
        except Exception as exc:
            engine.audit.log("op.ai.test", "failure", detail={"provider_key": body.provider_key}, client=_client(request))
            raise ApiError("ai_test_failed", f"test de connexion échoué : {exc}", 502) from exc
        _audit_op("op.ai.test", request, {"provider_key": body.provider_key, "ok": True})
        return result

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


def _profile_json(p) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "max_rebonds": p["max_rebonds"],
        "max_source_requests": p["max_source_requests"],
        "max_ai_calls": p["max_ai_calls"],
        "max_duration_seconds": p["max_duration_seconds"],
        "max_cost_cents": p["max_cost_cents"],
        "is_default": p["is_default"],
    }


def _health_json(report) -> dict:
    return {
        "connector_id": report.connector_id,
        "state": report.state.value,
        "checked_at": report.checked_at.isoformat(),
        "detail": report.detail,
        "http_status": report.http_status,
        "validation_problems": report.validation_problems,
        "probe_url": report.probe_url,
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
