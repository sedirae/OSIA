import pytest
from pydantic import ValidationError

from osia.ai import SimulatedAIAdapter
from osia.ai.schemas import Synthesis
from osia.models import PolicyDeny

from conftest import make_investigation


async def test_invalid_structured_output_is_rejected(engine):
    engine.broker.adapters["simulated"].scripted = {"synthesis": {"conclusion": 123}}
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny) as exc:
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert exc.value.reason == "sortie_ia_invalide"


async def test_paid_call_without_budget_is_denied(engine):
    paid = SimulatedAIAdapter(provider="cloud", model="payant-1", scripted={"synthesis": {"conclusion": "x", "support": "documenté"}})
    paid.paid = True
    paid.cost_per_call_cents = 10
    engine.broker.adapters["payant"] = paid
    engine.broker.role_models["synthesis"] = "payant"
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny):
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])


async def test_paid_call_with_unknown_cost_is_blocked(engine):
    paid = SimulatedAIAdapter(provider="cloud", model="payant-2", scripted={"synthesis": {"conclusion": "x", "support": "documenté"}})
    paid.paid = True
    paid.cost_per_call_cents = None
    engine.broker.adapters["payant2"] = paid
    engine.broker.role_models["synthesis"] = "payant2"
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny) as exc:
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert exc.value.reason == "cout_inconnu_bloque"


async def test_unauthorized_fallback_is_not_used(engine):
    engine.broker.adapters["simulated"].scripted = {"synthesis": {"conclusion": 123}}
    engine.broker.allowed_fallbacks = {}
    inv = await make_investigation(engine)
    with pytest.raises((PolicyDeny, ValidationError)):
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    events = await engine.repo.list_events(inv["id"])
    assert not any(e.type == "ai.fallback" for e in events)


async def test_authorized_fallback_used(engine):
    engine.broker.adapters["simulated"].scripted = {"synthesis": {"conclusion": 123}}
    alt = SimulatedAIAdapter(provider="local", model="local-1", scripted={"synthesis": {"conclusion": "ok", "support": "documenté"}})
    engine.broker.adapters["local"] = alt
    engine.broker.allowed_fallbacks = {"simulated": "local"}
    inv = await make_investigation(engine)
    out = await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert out.conclusion == "ok"
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "ai.fallback" for e in events)
