"""Configuration des fournisseurs depuis le web (D2 / CON-11), avec transport simulé."""

import hashlib
import json
import socket

import pytest
from httpx import ASGITransport, AsyncClient

from osia.ai import ChatCompletionsAdapter, PlanProposal
from osia.ai.connections import CONFIG_SETTING, ConnectionCredentials
from osia.api import create_app
from osia.engine import Engine
from osia.models import PolicyDeny
from osia.netguard import NetworkDeny

from conftest import make_investigation


SECRET = "test-key-never-returned"
MISTRAL = "/api/v1/ai/providers/mistral"
COMPATIBLE = "/api/v1/ai/providers/compatible"
SELECT = "/api/v1/ai/selection/"
PRICING = {"input_cents_per_mtok": 20, "output_cents_per_mtok": 60}


def client_for(engine, **kwargs):
    return AsyncClient(transport=ASGITransport(app=create_app(engine)), base_url="http://testserver", **kwargs)


async def test_web_mistral_configuration_routes_through_the_budget(engine, monkeypatch):
    calls = []

    async def models(adapter, url):
        calls.append(("GET", url, adapter._headers()))
        if adapter.api_key != SECRET:
            return 401, {}, adapter.api_key.encode()
        return 200, {}, json.dumps({"data": [{"id": "test-small"}, {"id": SECRET}]}).encode()

    async def completion(adapter, url, body):
        calls.append(("POST", url, adapter._headers()))
        assert body["model"] == "test-small"
        assert body["max_tokens"] > 0
        return 200, {}, json.dumps({
            "choices": [{"message": {"content": '{"sub_objectives": ["test"]}'}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 10},
        }).encode()

    monkeypatch.setattr(ChatCompletionsAdapter, "_get", models)
    monkeypatch.setattr(ChatCompletionsAdapter, "_post", completion)
    async with client_for(engine) as client:
        invalid = await client.post(MISTRAL + "/test", json={"api_key": "test-invalid"})
        assert invalid.status_code == 502 and "test-invalid" not in invalid.text
        result = await client.post(MISTRAL + "/test", json={"api_key": SECRET})
        assert result.status_code == 200 and result.json()["models"] == ["test-small"]
        assert calls[-1][:2] == ("GET", "https://api.mistral.ai/v1/models")
        assert calls[-1][2]["Authorization"] == f"Bearer {SECRET}"
        assert await engine.repo.get_setting(CONFIG_SETTING) is None
        saved = await client.put(MISTRAL, json={"model": "test-small", "api_key": SECRET, **PRICING})
        assert saved.status_code == 200 and saved.json()["selected"] == "simulated"
        assert SECRET not in saved.text
        chosen = await client.put(SELECT + "mistral")
        assert chosen.status_code == 200 and chosen.json()["active_model"] == "test-small"
        assert not await engine.repo.get_setting("paid_calls_enabled")
        inv = await make_investigation(engine)
        assert (await client.put(SELECT + "simulated")).status_code == 409

    with pytest.raises(PolicyDeny):
        await engine.broker.call("planning", "test", {}, PlanProposal, investigation_id=inv["id"])
    assert all(method == "GET" for method, _, _ in calls)
    await engine.repo.set_setting("paid_calls_enabled", True)
    result = await engine.broker.call("planning", "test", {}, PlanProposal, investigation_id=inv["id"])
    assert result.sub_objectives == ["test"]
    assert calls[-1][:2] == ("POST", "https://api.mistral.ai/v1/chat/completions")


async def test_compatible_configuration_restores_metadata_without_the_key(engine):
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"test-admin").hexdigest()
    headers = {"Authorization": "Bearer test-admin"}
    config = {"model": "sample/model", "base_url": "https://ai.example.com/v1", **PRICING}

    async with client_for(engine) as client:
        assert (await client.put(COMPATIBLE, json={**config, "api_key": SECRET})).status_code == 401
    async with client_for(engine, headers=headers) as client:
        invalid = await client.put(COMPATIBLE, json={**config, "api_key": [SECRET]})
        assert invalid.status_code == 422 and SECRET not in invalid.text
        assert (await client.put(COMPATIBLE, json={**config, "api_key": SECRET})).status_code == 200
        assert (await client.put(COMPATIBLE, json={**config, "base_url": "https://other.example.com/v1"})).status_code == 422
        assert (await client.put(SELECT + "compatible")).status_code == 200
        assert (await client.put(COMPATIBLE, json={**config, "base_url": "https://other.example.com/v1", "api_key": "new-test-key"})).status_code == 409
        assert SECRET not in (await client.get("/api/v1/ai/providers")).text
    assert SECRET not in json.dumps(await engine.repo.get_setting(CONFIG_SETTING))
    assert SECRET not in "".join(path.read_text() for path in engine.settings.paths.log_dir.glob("*.jsonl"))
    assert not (engine.settings.paths.config_dir / "secrets.enc").exists()

    restarted = Engine(engine.settings)
    await restarted.setup()
    try:
        async with client_for(restarted, headers=headers) as client:
            state = (await client.get("/api/v1/ai/providers")).json()
            assert state["selected"] == "compatible"
            assert state["configurations"]["compatible"]["model"] == config["model"]
            assert state["configurations"]["compatible"]["has_key"] is False
            denied = await client.post("/api/v1/investigations", json={"title": "test"})
            assert denied.status_code == 409 and denied.json()["error"]["code"] == "provider_unavailable"
            assert (await client.put(COMPATIBLE, json={**config, "api_key": SECRET})).status_code == 200
            assert restarted.broker.role_models["planning"] == "compatible"
    finally:
        await restarted.pool.close()


async def test_cloud_provider_rejects_private_addresses_and_redirects(engine):
    adapter = engine.ai_connections.test_adapter("compatible", ConnectionCredentials(
        base_url="https://ai.example.com/v1", api_key=SECRET,
    ))
    guard = adapter.netguard
    contacted = []

    async def fetch(url):
        contacted.append(url)
        return 307, {"location": "https://other.example.com/v1/models"}, b""

    async def resolve_private(host, port):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", port, 0, 0))]

    guard._resolver = resolve_private
    with pytest.raises(NetworkDeny, match="ssrf_ip_bloquee"):
        await guard.guarded_request(fetch, adapter.models_url)
    assert contacted == []

    async def resolve_public(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    guard._resolver = resolve_public
    with pytest.raises(NetworkDeny, match="trop_de_redirections"):
        await guard.guarded_request(fetch, adapter.models_url)
    assert contacted == [adapter.models_url]
    assert "ai.example.com" not in engine.netguard.policy.allowed_domains
