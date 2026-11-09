import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app

from conftest import make_investigation


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_api_investigation_crud_and_idempotency(engine):
    async with await client_for(engine) as client:
        r = await client.post("/api/v1/investigations", json={"title": "T1", "hints": ["a"]}, headers={"Idempotency-Key": "k1"})
        assert r.status_code == 201
        inv_id = r.json()["id"]
        assert r.json()["state"] == "running"
        r2 = await client.post("/api/v1/investigations", json={"title": "T1"}, headers={"Idempotency-Key": "k1"})
        assert r2.status_code == 200
        assert r2.json()["id"] == inv_id
        r3 = await client.post("/api/v1/investigations", json={"title": "AUTRE"}, headers={"Idempotency-Key": "k1"})
        assert r3.status_code == 409
        r = await client.get("/api/v1/investigations")
        assert any(i["id"] == inv_id for i in r.json())
        r = await client.get(f"/api/v1/investigations/{inv_id}")
        assert r.status_code == 200
        r = await client.get("/api/v1/investigations/inconnu")
        assert r.status_code == 404
        r = await client.get(f"/api/v1/investigations/{inv_id}/budget")
        assert r.json()["caps"]["investigation"] == 5
        assert r.json()["caps"]["global_month"] == 0
        r = await client.get(f"/api/v1/investigations/{inv_id}/events")
        types = [e["type"] for e in r.json()]
        assert "investigation.created" in types
        r = await client.get("/api/v1/profiles")
        assert {p["id"] for p in r.json()} == {"rapide", "standard", "approfondi"}
        r = await client.post(f"/api/v1/investigations/{inv_id}/stop", json={"reason": "user_interrupt"})
        assert r.json()["state"] == "stopped"
        r = await client.post(f"/api/v1/investigations/{inv_id}/branches", json={"objective": "b"})
        assert r.status_code == 403
        r = await client.post(
            f"/api/v1/investigations/{inv_id}/branches",
            json={"objective": "b", "explicit_acceptance": True, "limits": {"max_rebonds": 1}},
        )
        assert r.status_code == 201


async def test_server_mode_requires_auth(engine):
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"secret").hexdigest()
    async with await client_for(engine) as client:
        r = await client.get("/api/v1/health")
        assert r.status_code == 401
        r = await client.get("/api/v1/health", headers={"Authorization": "Bearer mauvais"})
        assert r.status_code == 401
        r = await client.get("/api/v1/health", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 200
    engine.settings.mode = "desktop"


async def test_sse_replay_with_cursor(engine):
    import asyncio

    import uvicorn

    inv = await make_investigation(engine, title="sse")
    app = create_app(engine)
    config = uvicorn.Config(app, host="127.0.0.1", port=18471, log_level="error")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    try:
        collected = ""
        async with AsyncClient(base_url="http://127.0.0.1:18471", timeout=10, trust_env=False) as client:
            async with client.stream(
                "GET", f"/api/v1/investigations/{inv['id']}/events", headers={"Accept": "text/event-stream"}
            ) as r:
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/event-stream")
                async for chunk in r.aiter_text():
                    collected += chunk
                    if "event: investigation.created" in collected:
                        break
        assert "event: investigation.created" in collected
        assert "id: " in collected
        assert "data: " in collected
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=10)
        except asyncio.TimeoutError:
            serve_task.cancel()


async def test_concurrent_same_idempotency_key_yields_one_investigation(engine):
    import asyncio

    async with await client_for(engine) as client:
        results = await asyncio.gather(
            *[
                client.post(
                    "/api/v1/investigations", json={"title": "race"}, headers={"Idempotency-Key": "race-key"}
                )
                for _ in range(2)
            ]
        )
        statuses = sorted(r.status_code for r in results)
        assert statuses == [200, 201]
        ids = {r.json()["id"] for r in results}
        assert len(ids) == 1
        count = await engine.pool.fetchval("SELECT COUNT(*) FROM investigations")
        assert int(count) == 1
