import pytest

from osia.models import PolicyDeny

from conftest import make_investigation


async def _mk_op(engine, inv_id):
    return await engine.repo.insert_op(investigation_id=inv_id, kind="ai_call", target="simulated:simulated-1")


async def test_reserve_is_idempotent(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    op = await _mk_op(engine, inv["id"])
    r1 = await engine.budgets.reserve(idempotency_key="k1", investigation_id=inv["id"], op_id=op["id"], amount_cents=3)
    r2 = await engine.budgets.reserve(idempotency_key="k1", investigation_id=inv["id"], op_id=op["id"], amount_cents=3)
    assert r1["id"] == r2["id"]
    count = await engine.pool.fetchval("SELECT COUNT(*) FROM reservations")
    assert count == 1


async def test_profile_cap_denies_overspend(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    op = await _mk_op(engine, inv["id"])
    await engine.budgets.reserve(idempotency_key="k1", investigation_id=inv["id"], op_id=op["id"], amount_cents=5)
    op2 = await _mk_op(engine, inv["id"])
    with pytest.raises(PolicyDeny) as exc:
        await engine.budgets.reserve(idempotency_key="k2", investigation_id=inv["id"], op_id=op2["id"], amount_cents=1)
    assert "investigation" in exc.value.reason


async def test_paid_disabled_blocks_any_paid_call(engine):
    inv = await make_investigation(engine)
    op = await _mk_op(engine, inv["id"])
    with pytest.raises(PolicyDeny) as exc:
        await engine.budgets.reserve(idempotency_key="k9", investigation_id=inv["id"], op_id=op["id"], amount_cents=1)
    assert "global_month" in exc.value.reason


async def test_global_monthly_cap(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    for i in range(5):
        inv = await make_investigation(engine, profile_id="approfondi")
        op = await _mk_op(engine, inv["id"])
        await engine.budgets.reserve(idempotency_key=f"g{i}", investigation_id=inv["id"], op_id=op["id"], amount_cents=100)
    inv6 = await make_investigation(engine, profile_id="approfondi")
    op6 = await _mk_op(engine, inv6["id"])
    with pytest.raises(PolicyDeny) as exc:
        await engine.budgets.reserve(idempotency_key="g5", investigation_id=inv6["id"], op_id=op6["id"], amount_cents=100)
    assert "global_month" in exc.value.reason


async def test_consume_reconcile_and_release(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    op = await _mk_op(engine, inv["id"])
    res = await engine.budgets.reserve(idempotency_key="c1", investigation_id=inv["id"], op_id=op["id"], amount_cents=4)
    op2 = await _mk_op(engine, inv["id"])
    res2 = await engine.budgets.reserve(idempotency_key="c2", investigation_id=inv["id"], op_id=op2["id"], amount_cents=1)
    await engine.budgets.consume(res["id"], actual_cents=5)
    kinds = await engine.pool.fetch("SELECT kind, amount_cents FROM ledger WHERE reservation_id = $1 ORDER BY id", res["id"])
    assert [(k["kind"], k["amount_cents"]) for k in kinds] == [("reserved", 4), ("consumed", 5), ("reconciled", 1)]
    await engine.budgets.release(res2["id"])
    state = await engine.pool.fetchval("SELECT state FROM reservations WHERE id = $1", res2["id"])
    assert state == "released"
    view = await engine.budgets.budget_view(inv["id"])
    assert view.consumed_cents == 5
    assert view.reserved_cents == 0


async def test_budget_view_caps(engine):
    inv = await make_investigation(engine)
    view = await engine.budgets.budget_view(inv["id"])
    assert view.caps["investigation"] == 5
    assert view.caps["global_month"] == 0
    assert view.available_cents == 0
