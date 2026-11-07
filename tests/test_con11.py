"""CON-11 (D2, T8, V1.3) : courtier IA réel — adaptateurs Mistral cloud et local
OpenAI-compatible, modèles par rôle, sorties structurées validées (T8.6), repli local->cloud
soumis à autorisation de transmission + budget (T8.8/T8.9, D2 §4.4).

Tous les appels passent par un `fetch_fn` injecté : aucun appel réseau/réel payant en test
(AGENTS.md, B6)."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from osia.ai import AIAdapterError, LocalOpenAIAdapter, MistralCloudAdapter, build_ai_adapters
from osia.ai.schemas import PlanProposal, Synthesis
from osia.api import create_app
from osia.config import Settings
from osia.models import PolicyDeny

from conftest import make_investigation


def chat_completion(payload: dict, status: int = 200) -> bytes:
    return json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}).encode("utf-8")


def fake_post(body: bytes, status: int = 200, capture: dict | None = None):
    async def fetch(url, payload, headers):
        if capture is not None:
            capture["url"] = url
            capture["payload"] = payload
            capture["headers"] = headers
        return status, {"content-type": "application/json"}, body

    return fetch


# ---------- Adaptateurs réels (contrat chat completions) ----------


async def test_mistral_complete_valide_sortie_structuree():
    capture = {}
    ad = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(chat_completion({"sub_objectives": ["a"], "reasoning": "r"}), capture=capture))
    out = await ad.complete("planning", "prompt système", {"objectif": "x"}, PlanProposal)
    assert out.sub_objectives == ["a"]
    assert capture["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert capture["payload"]["model"] == "mistral-small-2603"  # V1.3 : Small 4 par défaut
    assert capture["payload"]["response_format"] == {"type": "json_object"}
    assert capture["payload"]["messages"][0]["role"] == "system"
    assert capture["headers"]["Authorization"] == "Bearer sk-test"
    assert ad.paid is True and ad.cost_per_call_cents is not None  # borne connue (T8.4)


async def test_mistral_sortie_non_json_et_schema_invalide_rejetes():
    ad = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(b'{"choices":[{"message":{"content":"pas du json"}}]}'))
    with pytest.raises(AIAdapterError):
        await ad.complete("planning", "p", {}, PlanProposal)
    ad2 = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(chat_completion({"conclusion": 123})))
    with pytest.raises(ValidationError):  # T8.6 : schéma non conforme rejeté
        await ad2.complete("synthesis", "p", {}, Synthesis)


async def test_mistral_erreur_http_sans_fuite_de_cle():
    ad = MistralCloudAdapter(api_key="sk-test-secret", fetch_fn=fake_post(b"Unauthorized", status=401))
    with pytest.raises(AIAdapterError) as exc:
        await ad.complete("planning", "p", {}, PlanProposal)
    assert "sk-test-secret" not in str(exc.value)  # T8.8/D2 §4.3 : jamais de secret dans l'erreur
    assert exc.value.status == 401


async def test_ping_models_non_facture():
    capture = {}
    body = json.dumps({"data": [{"id": "mistral-small-2603"}, {"id": "mistral-large-latest"}]}).encode()
    ad = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(body, capture=capture))
    result = await ad.ping()
    assert result["ok"] is True
    assert "mistral-small-2603" in result["models"]
    assert capture["url"] == "https://api.mistral.ai/v1/models"  # GET /models : pas de prompt métier


async def test_local_adapter_host_local_hors_guard_et_non_payant():
    ad = LocalOpenAIAdapter(base_url="http://127.0.0.1:11434/v1", fetch_fn=fake_post(chat_completion({"conclusion": "ok", "support": "documenté"})))
    assert ad.is_local is True
    assert ad.netguard is None  # endpoint local explicite (T1), hors guard externe
    assert ad.paid is False
    out = await ad.complete("synthesis", "p", {}, Synthesis)
    assert out.conclusion == "ok"
    assert ad.model == "ministral-3-8b"  # V1.3 : premier candidat local


# ---------- Construction selon la configuration (D2 §4.2) ----------


def test_build_ai_adapters_simule_par_defaut(monkeypatch):
    monkeypatch.delenv("OSIA_MISTRAL_API_KEY", raising=False)
    adapters, roles, domains = build_ai_adapters(Settings(), None)
    assert set(adapters) == {"simulated"}  # aucun appel payant sans config explicite (B6/V1.4)
    assert set(roles.values()) == {"simulated"}
    assert domains == set()


def test_build_ai_adapters_local_et_mistral(monkeypatch):
    monkeypatch.setenv("OSIA_MISTRAL_API_KEY", "sk-env")
    settings = Settings(ai_local_base_url="http://127.0.0.1:11434/v1", ai_provider="local")
    adapters, roles, domains = build_ai_adapters(settings, None)
    assert set(adapters) == {"simulated", "local", "mistral"}
    assert roles["planning"] == "local"
    assert "api.mistral.ai" in domains  # domaine cloud à autoriser dans le guard
    assert adapters["mistral"].paid is True


def test_build_ai_adapters_cle_depuis_coffre(monkeypatch):
    from osia.security import SecretStore
    import tempfile, pathlib

    monkeypatch.delenv("OSIA_MISTRAL_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        store = SecretStore(pathlib.Path(tmp), persist=False)
        store.set("MISTRAL_API_KEY", "sk-coffre")
        adapters, _, _ = build_ai_adapters(Settings(), store)
        assert "mistral" in adapters


# ---------- Repli local -> cloud supervisé (T8.9, V1.3, D2 §4.4) ----------


async def test_repli_non_autorise_pas_utilise(engine):
    async def boom(url, payload, headers):
        raise AIAdapterError("local indisponible")

    engine.broker.adapters["local"] = LocalOpenAIAdapter(base_url="http://127.0.0.1:11434/v1", fetch_fn=boom)
    engine.broker.adapters["mistral"] = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(chat_completion({"conclusion": "ok", "support": "documenté"})))
    engine.broker.role_models["synthesis"] = "local"
    engine.broker.allowed_fallbacks = {}  # pas d'autorisation de transmission
    inv = await make_investigation(engine)
    with pytest.raises(AIAdapterError):
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    events = await engine.repo.list_events(inv["id"])
    assert not any(e.type == "ai.fallback" for e in events)


async def test_repli_autorise_mais_sans_budget_payant_refuse(engine):
    """T8.9 : aucun fournisseur de secours payant sans autorisation budgétaire suffisante."""

    async def boom(url, payload, headers):
        raise AIAdapterError("local indisponible")

    engine.broker.adapters["local"] = LocalOpenAIAdapter(base_url="http://127.0.0.1:11434/v1", fetch_fn=boom)
    engine.broker.adapters["mistral"] = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(chat_completion({"conclusion": "ok", "support": "documenté"})))
    engine.broker.role_models["synthesis"] = "local"
    engine.broker.allowed_fallbacks = {"local": "mistral"}  # autorisation de transmission
    # paid_calls_enabled = False par défaut (V1.4 : budget 0 € au premier démarrage)
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny):
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "ai.fallback" for e in events)  # tentative tracée


async def test_repli_autorise_avec_budget_fonctionne(engine):
    async def boom(url, payload, headers):
        raise AIAdapterError("local indisponible")

    engine.broker.adapters["local"] = LocalOpenAIAdapter(base_url="http://127.0.0.1:11434/v1", fetch_fn=boom)
    engine.broker.adapters["mistral"] = MistralCloudAdapter(api_key="sk-test", fetch_fn=fake_post(chat_completion({"conclusion": "ok cloud", "support": "documenté"})))
    engine.broker.role_models["synthesis"] = "local"
    engine.broker.allowed_fallbacks = {"local": "mistral"}
    await engine.repo.set_setting("paid_calls_enabled", True)  # enveloppe activée (V1.4)
    inv = await make_investigation(engine)
    out = await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert out.conclusion == "ok cloud"
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "ai.fallback" for e in events)


# ---------- API ----------


async def test_api_ai_providers_fallback_test(engine):
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.get("/api/v1/ai/providers")
        assert r.status_code == 200
        body = r.json()
        keys = {p["key"] for p in body["providers"]}
        assert "simulated" in keys
        assert body["fallback_local_to_cloud_authorized"] is False
        # aucune clé API exposée
        assert "sk-" not in json.dumps(body)

        r = await client.post("/api/v1/ai/fallback", json={"enabled": True})
        assert r.status_code == 200
        assert r.json()["allow_ai_fallback_local_to_cloud"] is True
        assert await engine.repo.get_setting("allow_ai_fallback_local_to_cloud") is True

        r = await client.post("/api/v1/ai/test", json={"provider_key": "simulated"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r = await client.post("/api/v1/ai/test", json={"provider_key": "inconnu"})
        assert r.status_code == 404
