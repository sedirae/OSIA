import asyncio

import pytest

from osia.models import PolicyDeny

from conftest import make_investigation


async def test_claim_is_unique_under_concurrency(engine):
    inv = await make_investigation(engine)
    await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    results = await asyncio.gather(*[engine.repo.claim_next_task() for _ in range(5)])
    claimed = [r for r in results if r is not None and r["kind"] == "noop"]
    assert len(claimed) == 1
    assert claimed[0]["state"] == "claimed"


async def test_recover_marks_uncertain_and_suspends(engine):
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    await engine.repo.set_task_state(task["id"], "running")
    op = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    await engine.repo.set_op_state(op["id"], "in_flight")
    report = await engine.scheduler.recover()
    assert report["ops_uncertain"] == 1
    assert report["investigations_suspended"] == 1
    assert (await engine.repo.get_task(task["id"]))["state"] == "interrupted"
    assert (await engine.repo.get_op(op["id"]))["state"] == "uncertain"
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "suspended"


async def test_resume_requeues_interrupted_tasks(engine):
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    await engine.repo.set_task_state(task["id"], "running")
    await engine.scheduler.recover()
    assert (await engine.repo.get_task(task["id"]))["state"] == "interrupted"
    await engine.orchestrator.resume(inv["id"])
    assert (await engine.repo.get_task(task["id"]))["state"] == "queued"
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "running"


async def test_scheduler_does_not_claim_tasks_of_suspended_investigation(engine):
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    await engine.repo.set_investigation_state(inv["id"], "suspended")
    claimed = await engine.repo.claim_next_task()
    assert claimed is None
    assert (await engine.repo.get_task(task["id"]))["state"] == "queued"


async def test_handler_execution_and_events(engine):
    async def noop(task, ctx):
        return {"ok": True}

    engine.scheduler.handlers["noop"] = noop
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    await engine.start()
    try:
        for _ in range(100):
            row = await engine.repo.get_task(task["id"])
            if row["state"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)
        assert row["state"] == "succeeded"
        events = await engine.repo.list_events(inv["id"])
        types = [e.type for e in events]
        assert "task.claimed" in types and "task.succeeded" in types
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_connector_failure_marks_op_uncertain(engine):
    from osia.connectors.simulated import SimulatedConnector

    class FailingConnector(SimulatedConnector):
        async def fetch(self, request):
            raise RuntimeError("source indisponible")

    failing = FailingConnector()
    failing.manifest.id = "simulated.failing"
    engine.registry.register(failing)
    engine.policy.allow_target("simulated.failing")
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], kind="source_query", payload={"query": "q", "connector_id": "simulated.failing"}
    )
    await engine.start()
    try:
        for _ in range(100):
            row = await engine.repo.get_task(task["id"])
            if row["state"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)
        assert row["state"] == "failed"
        op = await engine.pool.fetchrow(
            "SELECT * FROM external_ops WHERE task_id = $1", task["id"]
        )
        assert op["state"] == "uncertain"
        events = await engine.repo.list_events(inv["id"])
        assert any(e.type == "op.uncertain" for e in events)
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_connector_timeout_applies_limit(engine):
    from osia.connectors.simulated import SimulatedConnector

    class SlowConnector(SimulatedConnector):
        async def fetch(self, request):
            await asyncio.sleep(5)
            return await super().fetch(request)

    slow = SlowConnector()
    slow.manifest.id = "simulated.slow"
    engine.registry.register(slow)
    engine.policy.allow_target("simulated.slow")
    inv = await make_investigation(engine, limits={"http_timeout_seconds": 1})
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], kind="source_query", payload={"query": "q", "connector_id": "simulated.slow"}
    )
    await engine.start()
    try:
        for _ in range(100):
            row = await engine.repo.get_task(task["id"])
            if row["state"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.1)
        assert row["state"] == "failed"
        assert "TimeoutError" in (row["error"] or "") or "timeout" in (row["error"] or "").lower()
        op = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE task_id = $1", task["id"])
        assert op["state"] == "uncertain"
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner


async def test_resume_requires_reconciliation_then_works(engine):
    inv = await make_investigation(engine)
    task = await engine.repo.insert_task(investigation_id=inv["id"], kind="noop", payload={})
    await engine.repo.set_task_state(task["id"], "running")
    op = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    await engine.repo.set_op_state(op["id"], "in_flight")
    await engine.scheduler.recover()
    with pytest.raises(PolicyDeny) as exc:
        await engine.orchestrator.resume(inv["id"])
    assert "reconciliation_requise" in exc.value.reason
    reconciled = await engine.policy.reconcile_uncertain(op["id"], billed=False)
    assert reconciled["state"] == "reconciled"
    await engine.orchestrator.resume(inv["id"])
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "running"
    assert (await engine.repo.get_task(task["id"]))["state"] == "queued"
