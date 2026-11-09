"""Incidents reproduits lors de la revue globale après les PR #29 et #30."""

import asyncio
import io
import json
import zipfile
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from osia.ai.real import ChatCompletionsAdapter
from osia.ai.schemas import PlanProposal
from osia.api import create_app
from osia.config import ConfigError, Settings
from osia.engine import Engine
from osia.exchange.archive import ArchiveError, read_and_verify
from osia.models import CreateBranchRequest
from osia.models import OpKind, PolicyDeny
from osia.tasks import _build_synthesis_input

from conftest import make_investigation


@pytest.mark.parametrize("mode", ["Server", "serveur", "", "invalid"])
def test_invalid_mode_cannot_disable_server_security(mode):
    with pytest.raises(ConfigError):
        Settings(mode=mode, listen_host="0.0.0.0").validate_runtime()


async def test_settings_and_disabled_connectors_survive_restart(engine):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engine)), base_url="http://127.0.0.1") as client:
        response = await client.put("/api/v1/settings", json={"settings": {
            "session_ttl_hours": 2, "audit_retention_days": 7,
        }})
        assert response.status_code == 200
        response = await client.post("/api/v1/connectors/web.url/toggle", json={"enabled": False})
        assert response.status_code == 200
    restarted = Engine(replace(engine.settings))
    try:
        await restarted.setup()
        assert restarted.sessions.ttl == timedelta(hours=2)
        assert restarted.audit.retention_days == 7
        assert restarted.registry.get("web.url") is None
    finally:
        await restarted.pool.close()


async def test_second_engine_cannot_recover_live_tasks(engine):
    entered = asyncio.Event()
    hold = asyncio.Event()

    async def long_task(task, ctx):
        entered.set()
        await hold.wait()
        return {}

    engine.scheduler.handlers = {"plan": long_task}
    inv = await make_investigation(engine)
    other = Engine(replace(engine.settings))
    await other.setup()
    try:
        await engine.start()
        await asyncio.wait_for(entered.wait(), 3)
        with pytest.raises(ConfigError, match="déjà"):
            await other.start()
        assert (await engine.repo.get_investigation(inv["id"]))["state"] == "running"
        assert (await engine.repo.list_tasks(inv["id"]))[0]["state"] == "running"
    finally:
        await other.stop()
        await engine.stop()


@pytest.mark.parametrize("usage", [
    {}, [], "invalid", {"prompt_tokens": 100},
    {"prompt_tokens": -100, "completion_tokens": 10},
    {"prompt_tokens": True, "completion_tokens": 10},
    {"prompt_tokens": "not-a-number", "completion_tokens": 10},
    {"prompt_tokens": 1.5, "completion_tokens": 10},
])
async def test_malformed_usage_keeps_cost_uncertain(engine, usage):
    async def fetch(url, payload, headers):
        return 200, {}, json.dumps({"choices": [{"message": {"content": "{}"}}], "usage": usage}).encode()

    adapter = ChatCompletionsAdapter(
        provider="cloud", model="test", base_url="https://provider.test", paid=True,
        input_cents_per_mtok=100, output_cents_per_mtok=100, max_output_tokens=10, fetch_fn=fetch,
    )
    await engine.repo.set_setting("paid_calls_enabled", True)
    engine.broker.adapters["cloud"] = adapter
    engine.broker.role_models["planning"] = "cloud"
    inv = await make_investigation(engine)
    await engine.broker.call("planning", "p", {}, PlanProposal, investigation_id=inv["id"])
    row = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE investigation_id=$1", inv["id"])
    assert row["state"] == "uncertain"
    view = await engine.budgets.budget_view(inv["id"])
    assert view.consumed_cents == 0 and view.uncertain_cents > 0


@pytest.mark.parametrize("entry", [None, [], 123, "file"])
def test_malformed_archive_entries_raise_domain_error(entry):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "format": "osia-archive", "format_version": "1.0", "files": [entry],
        }))
    buffer.seek(0)
    with pytest.raises(ArchiveError):
        read_and_verify(buffer)


@pytest.mark.parametrize("body", [b"{", b"[]", b'{"path":123}', b'{"path":"/does/not/exist"}'])
async def test_import_preview_invalid_input_is_not_internal_error(engine, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engine), raise_app_exceptions=False), base_url="http://127.0.0.1") as client:
        response = await client.post("/api/v1/import/preview", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code in (400, 422)
    assert "error" in response.json()


async def test_cache_distinguishes_request_parameters(engine):
    await engine.repo.cache_set("api.test", "q", {"content": "page one"}, 24, params={"page": 1})
    assert await engine.repo.cache_get("api.test", "q", params={"page": 2}) is None
    assert (await engine.repo.cache_get("api.test", "q", params={"page": 1}))["content"] == "page one"


async def test_synthesis_uses_branch_objective(engine):
    inv = await make_investigation(engine, objective="Objectif parent")
    branch = await engine.orchestrator.create_branch(inv["id"], CreateBranchRequest(
        objective="Vérifier une filiale", explicit_acceptance=True,
    ))
    task = {"branch_id": branch["id"], "depth": 0}
    data, _ = await _build_synthesis_input(engine, inv, task)
    assert data["objective"] == "Vérifier une filiale"


async def test_resume_rechecks_state_after_waiting_for_lock(engine):
    inv = await make_investigation(engine)
    await engine.orchestrator.suspend(inv["id"])
    async with engine.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT id FROM investigations WHERE id=$1 FOR UPDATE", inv["id"])
            resume = asyncio.create_task(engine.orchestrator.resume(inv["id"]))
            await asyncio.sleep(0.05)
            await conn.execute("UPDATE investigations SET state='stopped' WHERE id=$1", inv["id"])
    with pytest.raises(PolicyDeny, match="reprise_impossible"):
        await asyncio.wait_for(resume, 3)
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "stopped"


async def test_stop_and_revalidate_do_not_deadlock(engine):
    inv = await make_investigation(engine)
    decision = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.SOURCE_REQUEST, target="simulated.web",
        is_paid=False, cost_estimated_cents=None,
    )
    async with engine.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT id FROM investigations WHERE id=$1 FOR UPDATE", inv["id"])
            check = asyncio.create_task(engine.policy.revalidate(decision.op_id, investigation_id=inv["id"]))
            await asyncio.sleep(0.05)
            await asyncio.wait_for(conn.execute("UPDATE external_ops SET state='cancelled' WHERE id=$1", decision.op_id), 2)
    assert not (await asyncio.wait_for(check, 2)).allowed


async def test_migrations_can_run_concurrently_on_empty_database(pg_server):
    import asyncpg
    import secrets
    from osia.store.db import create_pool, migrate

    name = "osia_migrate_" + secrets.token_hex(4)
    admin = await asyncpg.connect(pg_server.get_uri())
    await admin.execute(f'CREATE DATABASE "{name}"')
    pools = []
    try:
        pools = [await create_pool(pg_server.get_uri(database=name)) for _ in range(3)]
        results = await asyncio.gather(*(migrate(pool) for pool in pools))
        assert sorted(sum(results, [])) == [1, 2, 3, 4, 5, 6]
        assert await pools[0].fetchval("SELECT COUNT(*) FROM schema_migrations") == 6
    finally:
        for pool in pools:
            await pool.close()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def test_oversized_streamed_upload_is_rejected_and_cleaned(engine, monkeypatch):
    import importlib
    api_module = importlib.import_module("osia.api.app")
    monkeypatch.setattr(api_module, "MAX_IMPORT_UPLOAD_BYTES", 10)

    async def chunks():
        yield b"123456"
        yield b"789012"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engine)), base_url="http://127.0.0.1") as client:
        response = await client.post("/api/v1/import/preview", content=chunks(), headers={"Content-Type": "application/octet-stream"})
        assert response.status_code == 413
        response = await client.post("/api/v1/import/apply", json={"path": 123, "passphrase": "private-test-passphrase"})
        assert response.status_code == 400 and "private-test-passphrase" not in response.text
    assert not list(engine.settings.paths.incoming_dir.glob("upload_*"))


async def test_archive_missing_primary_key_is_rejected(engine, tmp_path):
    from osia.exchange.archive import write_archive
    archive = tmp_path / "missing-id.osia"
    write_archive(archive, payload={"investigations": [{"title": "sans identifiant"}]}, proofs={},
                  scope={}, warnings=[], osia_version="0.1.0")
    with pytest.raises(ArchiveError):
        await engine.exchange.preview_import(archive)
    with pytest.raises(ArchiveError):
        await engine.exchange.apply_import(archive)
    assert not await engine.repo.list_investigations()


async def test_billing_failure_rolls_back_operation_and_ledger_together(engine, monkeypatch):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    decision = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.AI_CALL, target="simulated:simulated-1",
        is_paid=True, cost_estimated_cents=2,
    )
    await engine.policy.mark_in_flight(decision.op_id)
    consume = engine.budgets.consume_in_conn

    async def fail_after_write(conn, reservation_id, amount):
        await consume(conn, reservation_id, amount)
        raise RuntimeError("incident après écriture")

    monkeypatch.setattr(engine.budgets, "consume_in_conn", fail_after_write)
    with pytest.raises(RuntimeError):
        await engine.policy.complete_op(decision.op_id, {}, actual_cents=1)
    assert (await engine.repo.get_op(decision.op_id))["state"] == "in_flight"
    assert await engine.pool.fetchval("SELECT state FROM reservations WHERE id=$1", decision.reservation_id) == "reserved"
    assert await engine.pool.fetchval("SELECT COUNT(*) FROM ledger WHERE kind='consumed'") == 0


async def test_stop_during_reservation_does_not_resurrect_operation(engine, monkeypatch):
    from osia.models import StopReason
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    reserve = engine.budgets.reserve

    async def reserve_then_stop(**kwargs):
        result = await reserve(**kwargs)
        await engine.orchestrator.stop(inv["id"], StopReason.USER)
        return result

    monkeypatch.setattr(engine.budgets, "reserve", reserve_then_stop)
    decision = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.AI_CALL, target="simulated:simulated-1",
        is_paid=True, cost_estimated_cents=2,
    )
    assert not decision.allowed
    assert (await engine.repo.get_op(decision.op_id))["state"] == "cancelled"
    assert (await engine.budgets.budget_view(inv["id"])).reserved_cents == 0


async def test_source_cache_does_not_reuse_another_page(engine):
    from osia.tasks import TaskContext, handle_source_query
    connector = engine.registry.get("simulated.web")
    inv = await make_investigation(engine)
    for page in (1, 2, 2):
        task = await engine.repo.insert_task(
            investigation_id=inv["id"], kind="source_query",
            payload={"query": "q", "connector_id": "simulated.web", "params": {"page": page}},
        )
        await handle_source_query(task, TaskContext(engine))
    assert connector.calls == ["q", "q"]


async def test_local_api_rejects_foreign_host_and_origin(engine):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engine)), base_url="http://127.0.0.1") as client:
        assert (await client.get("/api/v1/health", headers={"Host": "untrusted.example"})).status_code == 400
        assert (await client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})).status_code == 403
        assert (await client.get("/api/v1/health", headers={"Origin": "null"})).status_code == 403
        assert (await client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1"})).status_code == 200


async def test_encrypted_upload_uses_header_and_rejects_url_secret(engine, tmp_path):
    import base64
    from osia.exchange.archive import write_archive
    secret = "phrase chiffrée de recette"
    archive = tmp_path / "encrypted.osia"
    write_archive(archive, payload={}, proofs={}, scope={}, warnings=[], osia_version="0.1.0",
                  encrypt=True, passphrase=secret)
    headers = {"Content-Type": "application/octet-stream",
               "X-OSIA-Archive-Passphrase-B64": base64.b64encode(secret.encode()).decode()}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engine)), base_url="http://127.0.0.1") as client:
        response = await client.post("/api/v1/import/preview", content=archive.read_bytes(), headers=headers)
        assert response.status_code == 200 and response.json()["encrypted"] is True
        response = await client.post("/api/v1/import/apply?passphrase=secret", content=archive.read_bytes(), headers=headers)
        assert response.status_code == 400
        response = await client.post("/api/v1/import/apply", content=archive.read_bytes(), headers=headers)
        assert response.status_code == 201
