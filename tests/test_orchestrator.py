import asyncio
import json

import pytest

from osia.models import CreateBranchRequest, PolicyDeny, StopReason

from conftest import make_investigation


async def wait_state(engine, inv_id, states, timeout=10.0):
    for _ in range(int(timeout / 0.05)):
        inv = await engine.repo.get_investigation(inv_id)
        if inv["state"] in states:
            return inv
        await asyncio.sleep(0.05)
    return await engine.repo.get_investigation(inv_id)


async def test_start_is_idempotent(engine):
    from osia.models import CreateInvestigationRequest

    req = CreateInvestigationRequest(title="idem", idempotency_key="key-1")
    inv1 = await engine.orchestrator.start_investigation(req)
    inv2 = await engine.orchestrator.start_investigation(req)
    assert inv1["id"] == inv2["id"]


async def test_branch_requires_explicit_acceptance_and_caps(engine):
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny):
        await engine.orchestrator.create_branch(inv["id"], CreateBranchRequest(objective="branche"))
    with pytest.raises(PolicyDeny):
        await engine.orchestrator.create_branch(
            inv["id"],
            CreateBranchRequest(objective="branche", explicit_acceptance=True, limits={"max_cost_cents": 999}),
        )
    branch = await engine.orchestrator.create_branch(
        inv["id"],
        CreateBranchRequest(objective="branche ok", explicit_acceptance=True, limits={"max_rebonds": 1}),
    )
    assert branch["state"] == "running"
    assert branch["effective_limits"]["max_rebonds"] == 1


async def test_stop_cancels_queued_tasks(engine):
    inv = await make_investigation(engine)
    await engine.orchestrator.stop(inv["id"], StopReason.USER)
    inv = await engine.repo.get_investigation(inv["id"])
    assert inv["state"] == "stopped"
    assert inv["stop_reason"] == "user_interrupt"
    tasks = await engine.repo.list_tasks(inv["id"])
    assert all(t["state"] == "cancelled" for t in tasks)


async def test_vertical_run_objective_reached(engine):
    engine.broker.adapters["simulated"].scripted = {
        "planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
        "extraction": {"entities": [{"kind": "entreprise", "name": "ACME", "identifiers": {"siren": "123456789"}}], "relations": []},
        "synthesis": {"conclusion": "ACME existe", "support": "documenté", "decisive_sources": ["https://ex.test/1"], "objective_sufficiently_supported": True},
    }
    await engine.start()
    inv = await make_investigation(engine, title="verticale", objective="Vérifier ACME")
    try:
        final = await wait_state(engine, inv["id"], {"stopped", "error"})
        assert final["state"] == "stopped"
        assert final["stop_reason"] == "objective_suffisamment_etaye"
        tasks = await engine.repo.list_tasks(inv["id"])
        kinds = {t["kind"]: t["state"] for t in tasks}
        assert kinds.get("plan") == "succeeded"
        assert kinds.get("source_query") == "succeeded"
        assert kinds.get("synthesize") == "succeeded"
        proofs = await engine.repo.list_proof_refs(inv["id"])
        assert len(proofs) == 1
        entities = await engine.pool.fetch("SELECT * FROM entities WHERE investigation_id = $1", inv["id"])
        assert len(entities) == 1
        data = entities[0]["data"]
        if isinstance(data, str):
            data = json.loads(data)
        assert data["name"] == "ACME"
        assertions = await engine.pool.fetch("SELECT * FROM assertions WHERE investigation_id = $1", inv["id"])
        assert len(assertions) == 1
        events = await engine.repo.list_events(inv["id"])
        types = [e.type for e in events]
        assert "discovery" in types and "investigation.stopped" in types
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_rebonds_until_depth_limit(engine):
    engine.broker.adapters["simulated"].scripted = {
        "planning": {"sub_objectives": [], "source_queries": ["q0"]},
        "extraction": {"entities": [], "relations": []},
        "synthesis": [
            {"conclusion": "partiel", "support": "à confirmer", "suggested_followups": ["q1"], "objective_sufficiently_supported": False},
            {"conclusion": "partiel", "support": "à confirmer", "suggested_followups": ["q2"], "objective_sufficiently_supported": False},
            {"conclusion": "partiel", "support": "à confirmer", "suggested_followups": ["q3"], "objective_sufficiently_supported": False},
        ],
    }
    await engine.start()
    inv = await make_investigation(engine, profile_id="approfondi", limits={"max_rebonds": 2})
    try:
        final = await wait_state(engine, inv["id"], {"stopped", "error"})
        assert final["stop_reason"] == "depth_limit"
        tasks = await engine.repo.list_tasks(inv["id"])
        sq = [t for t in tasks if t["kind"] == "source_query"]
        assert sorted(t["depth"] for t in sq) == [0, 1, 2]
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_budget_exhaustion_stops_investigation(engine):
    from osia.ai import SimulatedAIAdapter

    await engine.repo.set_setting("paid_calls_enabled", True)
    paid = SimulatedAIAdapter(
        provider="cloud",
        model="payant-1",
        scripted={"planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]}},
    )
    paid.paid = True
    paid.cost_per_call_cents = 10
    engine.broker.adapters["payant"] = paid
    engine.broker.role_models["planning"] = "payant"
    engine.policy.allow_target("cloud:payant-1")
    await engine.start()
    try:
        inv = await make_investigation(engine, title="budget", limits={"max_cost_cents": 5})
        final = await wait_state(engine, inv["id"], {"stopped", "error"})
        assert final["state"] == "stopped"
        assert final["stop_reason"] == "budget_exhausted"
        tasks = await engine.repo.list_tasks(inv["id"])
        plan = [t for t in tasks if t["kind"] == "plan"]
        assert plan and plan[0]["state"] == "failed"
        assert "plafond" in plan[0]["error"]
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_limits_come_from_profiles_table(engine):
    await engine.pool.execute("UPDATE profiles SET max_source_requests = 7 WHERE id = 'rapide'")
    inv = await make_investigation(engine)
    limits = inv["effective_limits"]
    if isinstance(limits, str):
        limits = json.loads(limits)
    assert limits["max_source_requests"] == 7


async def test_branch_depth_inherited_and_parent_checked(engine):
    inv = await make_investigation(engine)
    b1 = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="b1", explicit_acceptance=True)
    )
    assert b1["depth"] == 0
    b2 = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="b2", explicit_acceptance=True, parent_branch_id=b1["id"])
    )
    assert b2["depth"] == 1
    other = await make_investigation(engine, title="autre")
    with pytest.raises(PolicyDeny):
        await engine.orchestrator.create_branch(
            other["id"],
            CreateBranchRequest(objective="x", explicit_acceptance=True, parent_branch_id=b1["id"]),
        )
