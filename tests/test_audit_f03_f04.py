"""Régression audit issue #17 — F03 (coûts réels/usage, réconciliation, séparation
estimé/réservé/constaté/incertain) et F04 (limites effectives à l'envoi : admission atomique,
branche, durée, revalidation avant I/O, arrêt).

Inversion des sondes de l'annexe de l'audit. Les tests `engine` utilisent PostgreSQL de test
local (pgserver) ; les tests courtier avec doubles restent hors ligne."""

import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from osia.ai import SimulatedAIAdapter
from osia.ai.broker import AIBroker
from osia.ai.real import ChatCompletionsAdapter
from osia.ai.schemas import PlanProposal, Synthesis
from osia.models import CreateBranchRequest, OpKind, PolicyDeny, StopReason
from osia.scheduler import Scheduler

from conftest import make_investigation


# ---------- F03 : coûts ----------


async def test_f03_payload_contient_plafond_sortie_et_usage_constate():
    """Le payload envoyé au fournisseur contient max_tokens (borne de sortie) et l'usage de la
    réponse est conservé ; le coût constaté vient de l'usage, pas du forfait."""
    captured = {}

    async def fetch(url, payload, headers):
        captured["payload"] = payload
        body = {
            "choices": [{"message": {"content": json.dumps({"source_queries": ["q"]})}}],
            "usage": {"prompt_tokens": 2_000_000, "completion_tokens": 3_000_000},
        }
        return 200, {}, json.dumps(body).encode()

    adapter = ChatCompletionsAdapter(
        provider="t", model="m", base_url="https://m.test", paid=True, cost_per_call_cents=99,
        input_cents_per_mtok=1, output_cents_per_mtok=1, max_output_tokens=100, fetch_fn=fetch,
    )
    out, usage = await adapter.complete_with_usage("planning", "p", {"objective": "o"}, PlanProposal)
    assert out.source_queries == ["q"]
    assert captured["payload"]["max_tokens"] == 100  # borne de sortie envoyée (F03)
    assert usage == {"prompt_tokens": 2_000_000, "completion_tokens": 3_000_000}
    # borne = ceil((entrée estimée + plafond sortie) * tarif / 1e6) ; constat = usage réel
    est = adapter.estimate_cost_cents(adapter.estimate_input_tokens("p", {"objective": "o"}), adapter.max_output_tokens)
    assert est == 1  # ~2 tokens entrée + 100 sortie -> 1 centime
    assert adapter.actual_cost_cents(usage) == 5  # 5M tokens -> 5 centimes, != forfait 99
    assert adapter.actual_cost_cents(None) is None  # usage absent -> inconnu, jamais l'estimation


async def test_f03_courtier_constate_usage_reel_pas_estimation(engine):
    """Le registre constate le coût calculé depuis l'usage (5 c), pas le forfait (99 c) ni
    l'estimation (1 c) ; l'écart réservation/facturation est visible au ledger."""

    class PaidAdapter(SimulatedAIAdapter):
        def __init__(self):
            super().__init__(provider="cloud", model="payant", scripted={"synthesis": {"conclusion": "x", "support": "documenté"}})
            self.paid = True
            self.cost_per_call_cents = 99  # forfait délibérément faux
            self.max_output_tokens = 100

        def estimate_cost_cents(self, input_tokens, max_output_tokens):
            return -(-(input_tokens + (max_output_tokens or 0)) // 1_000_000)

        def actual_cost_cents(self, usage):
            if usage is None:
                return None
            return -(-(usage["prompt_tokens"] + usage["completion_tokens"]) // 1_000_000)

        async def complete_with_usage(self, role, prompt, input_data, response_model):
            out = await self.complete(role, prompt, input_data, response_model)
            return out, {"prompt_tokens": 2_000_000, "completion_tokens": 3_000_000}

    await engine.repo.set_setting("paid_calls_enabled", True)
    engine.broker.adapters["payant"] = PaidAdapter()
    engine.broker.role_models["synthesis"] = "payant"
    inv = await make_investigation(engine)
    out = await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert out.conclusion == "x"
    op = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE investigation_id = $1 ORDER BY created_at DESC LIMIT 1", inv["id"])
    assert op["state"] == "completed"
    assert op["cost_estimated_cents"] == 1  # borne token, pas le forfait 99
    ledger = await engine.pool.fetch(
        "SELECT kind, amount_cents FROM ledger WHERE reservation_id = $1 ORDER BY id", op["reservation_id"]
    )
    kinds = [(r["kind"], r["amount_cents"]) for r in ledger]
    assert ("reserved", 1) in kinds and ("consumed", 5) in kinds and ("reconciled", 4) in kinds
    view = await engine.budgets.budget_view(inv["id"])
    assert view.consumed_cents == 5  # constaté réel
    assert view.reserved_cents == 0
    assert view.estimated_cents == 0  # op terminée : plus aucun devis en cours


async def test_f03_sortie_invalide_mais_facturee_est_reconciliee(engine):
    """Une sortie IA invalide (ValidationError) APRÈS l'appel laisse la réservation active dans
    l'ancien code ; ici elle est consommée avec le coût réel (usage) et l'op passe 'failed'."""

    async def fetch(url, payload, headers):
        body = {
            "choices": [{"message": {"content": json.dumps({"conclusion": 123})}}],  # invalide pour Synthesis
            "usage": {"prompt_tokens": 2_000_000, "completion_tokens": 3_000_000},
        }
        return 200, {}, json.dumps(body).encode()

    adapter = ChatCompletionsAdapter(
        provider="t", model="m", base_url="https://m.test", paid=True, cost_per_call_cents=99,
        input_cents_per_mtok=1, output_cents_per_mtok=1, max_output_tokens=100, fetch_fn=fetch,
    )
    await engine.repo.set_setting("paid_calls_enabled", True)
    engine.broker.adapters["t"] = adapter
    engine.broker.role_models["synthesis"] = "t"
    inv = await make_investigation(engine)
    with pytest.raises(PolicyDeny) as exc:
        await engine.broker.call("synthesis", "p", {}, Synthesis, investigation_id=inv["id"])
    assert exc.value.reason == "sortie_ia_invalide"
    op = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE investigation_id = $1 ORDER BY created_at DESC LIMIT 1", inv["id"])
    assert op["state"] == "failed"
    res = await engine.pool.fetchrow("SELECT * FROM reservations WHERE id = $1", op["reservation_id"])
    assert res["state"] == "consumed"  # facturé malgré la sortie invalide -> consommé (5 c), pas libéré
    consumed = await engine.pool.fetchval(
        "SELECT amount_cents FROM ledger WHERE reservation_id = $1 AND kind = 'consumed'", op["reservation_id"]
    )
    assert consumed == 5


async def test_f03_budget_view_separe_estime_reserve_constate_incertain(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    op_est = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1", cost_estimated_cents=3)
    await engine.pool.execute("UPDATE external_ops SET state = 'authorized' WHERE id = $1", op_est["id"])
    op_res = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    res = await engine.budgets.reserve(idempotency_key="v1", investigation_id=inv["id"], op_id=op_res["id"], amount_cents=1)
    await engine.pool.execute("UPDATE external_ops SET state = 'reserved', reservation_id = $2 WHERE id = $1", op_res["id"], res["id"])
    op_unc = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    res2 = await engine.budgets.reserve(idempotency_key="v2", investigation_id=inv["id"], op_id=op_unc["id"], amount_cents=2)
    await engine.pool.execute(
        "UPDATE external_ops SET state = 'uncertain', reservation_id = $2 WHERE id = $1", op_unc["id"], res2["id"]
    )
    view = await engine.budgets.budget_view(inv["id"])
    assert view.estimated_cents == 3  # devis de l'op admise non constatée
    assert view.reserved_cents == 3  # 1 (reserved) + 2 (uncertain)
    assert view.uncertain_cents == 2  # enveloppe à réconcilier
    assert view.consumed_cents == 0


# ---------- F04 : limites effectives à l'envoi ----------


async def test_f04_duree_max_atteinte_refusee(engine):
    """Sonde inversée : une investigation vieille d'un jour avec max_duration_seconds=120 doit
    être refusée (l'ancien code acceptait)."""
    inv = await make_investigation(engine)
    branch = (await engine.repo.list_branches(inv["id"]))[0]
    await engine.pool.execute(
        "UPDATE investigations SET created_at = now() - interval '1 day' WHERE id = $1", inv["id"]
    )
    d = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.SOURCE_REQUEST, target="simulated.web",
        is_paid=False, cost_estimated_cents=None, branch_id=branch["id"],
    )
    assert not d.allowed and d.reason == "duree_max_atteinte"


async def test_f04_branche_inconnue_refusee(engine):
    """Sonde inversée : une branche inexistante ne doit plus être acceptée."""
    inv = await make_investigation(engine)
    d = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.SOURCE_REQUEST, target="simulated.web",
        is_paid=False, cost_estimated_cents=None, branch_id="nonexistent_branch",
    )
    assert not d.allowed and d.reason == "branche_inconnue"


async def test_f04_limites_branche_appliquees_aux_operations_gratuites(engine):
    """Les limites de branche (max_source_requests=0) s'appliquent aussi aux opérations gratuites."""
    inv = await make_investigation(engine)
    parent = (await engine.repo.list_branches(inv["id"]))[0]
    branch = await engine.orchestrator.create_branch(
        inv["id"],
        CreateBranchRequest(objective="branche restreinte", parent_branch_id=parent["id"], limits={"max_source_requests": 0}, explicit_acceptance=True),
    )
    d = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.SOURCE_REQUEST, target="simulated.web",
        is_paid=False, cost_estimated_cents=None, branch_id=branch["id"],
    )
    assert not d.allowed and d.reason == "plafond_requetes_source_atteint"


async def test_f04_admission_atomique_sous_concurrence(engine):
    """5 autorisations concurrentes pour un quota de 2 requêtes source : exactement 2 admises
    (compteur + insert atomiques par verrou de ligne)."""
    inv = await make_investigation(engine, limits={"max_source_requests": 2})
    branch = (await engine.repo.list_branches(inv["id"]))[0]
    results = await asyncio.gather(*[
        engine.policy.authorize(
            investigation_id=inv["id"], kind=OpKind.SOURCE_REQUEST, target="simulated.web",
            is_paid=False, cost_estimated_cents=None, branch_id=branch["id"],
        )
        for _ in range(5)
    ])
    assert sum(1 for d in results if d.allowed) == 2
    assert sum(1 for d in results if not d.allowed and d.reason == "plafond_requetes_source_atteint") == 3


async def test_f04_revalidation_annule_envoi_apres_attente_semaphore():
    """Sonde audit inversée : une autorisation révoquée pendant l'attente du sémaphore ne doit
    PAS déclencher l'appel à l'adaptateur ; l'opération jamais envoyée est annulée (enveloppe
    libérée), pas passée en 'uncertain'."""
    state = {"allowed": True}

    async def authorize(**kw):
        return NS(allowed=True, op_id="op1", reservation_id="r1", timeout_seconds=60)

    async def revalidate(op_id, *, investigation_id):
        return NS(
            allowed=state["allowed"],
            reason=None if state["allowed"] else "investigation_non_active:stopped",
            op_id=op_id, reservation_id="r1", timeout_seconds=60,
        )

    cancelled = []

    async def cancel_op(op_id, *, reason):
        cancelled.append((op_id, reason))

    policy = NS(
        allow_target=lambda t: None,
        authorize=AsyncMock(side_effect=authorize),
        revalidate=AsyncMock(side_effect=revalidate),
        cancel_op=AsyncMock(side_effect=cancel_op),
        mark_in_flight=AsyncMock(), complete_op=AsyncMock(), mark_uncertain=AsyncMock(), fail_op=AsyncMock(),
    )
    adapter = NS(
        provider="t", model="m", paid=False, cost_per_call_cents=None, max_output_tokens=None,
        estimate_input_tokens=lambda p, d: 1, estimate_cost_cents=lambda i, m: None,
        actual_cost_cents=lambda u: None,
        complete=AsyncMock(return_value=PlanProposal()),
        complete_with_usage=AsyncMock(return_value=(PlanProposal(), None)),
    )
    sem = asyncio.Semaphore(0)
    broker = AIBroker(policy, NS(emit=AsyncMock()), {"t": adapter}, {"planning": "t"}, semaphore=sem)
    pending = asyncio.create_task(broker.call("planning", "p", {}, PlanProposal, investigation_id="i"))
    await asyncio.sleep(0.05)  # la tâche attend le créneau d'envoi
    state["allowed"] = False  # l'autorisation est révoquée pendant l'attente
    sem.release()
    with pytest.raises(PolicyDeny):
        await asyncio.wait_for(pending, 2)
    assert adapter.complete.await_count == 0
    assert adapter.complete_with_usage.await_count == 0
    assert cancelled == [("op1", "investigation_non_active:stopped")]
    policy.mark_uncertain.assert_not_awaited()  # jamais envoyée -> pas 'uncertain'


async def test_f04_stop_annule_les_runners_en_cours():
    sch = Scheduler(None, None, None, {}, engine=None)
    runner = asyncio.create_task(asyncio.sleep(30))
    sch._pending.add(runner)
    sch.stop()
    with pytest.raises(asyncio.CancelledError):
        await runner


async def test_f04_stop_libere_les_reservations_jamais_envoyees(engine):
    """stop() : une opération réservée mais jamais envoyée passe 'cancelled' et son enveloppe est
    libérée (released + ledger) ; une opération in_flight passe 'uncertain' (réconciliation)."""
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine)
    branch = (await engine.repo.list_branches(inv["id"]))[0]
    d = await engine.policy.authorize(
        investigation_id=inv["id"], kind=OpKind.AI_CALL, target="simulated:simulated-1",
        is_paid=True, cost_estimated_cents=2, branch_id=branch["id"],
    )
    assert d.allowed and d.reservation_id
    op2 = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1", is_paid=True, cost_estimated_cents=1)
    res2 = await engine.budgets.reserve(idempotency_key="stop2", investigation_id=inv["id"], op_id=op2["id"], amount_cents=1)
    await engine.pool.execute(
        "UPDATE external_ops SET state = 'in_flight', reservation_id = $2 WHERE id = $1", op2["id"], res2["id"]
    )
    await engine.orchestrator.stop(inv["id"], StopReason.USER)
    op1 = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE id = $1", d.op_id)
    assert op1["state"] == "cancelled"
    res1 = await engine.pool.fetchrow("SELECT * FROM reservations WHERE id = $1", d.reservation_id)
    assert res1["state"] == "released"
    op2row = await engine.pool.fetchrow("SELECT * FROM external_ops WHERE id = $1", op2["id"])
    assert op2row["state"] == "uncertain"
    res2row = await engine.pool.fetchrow("SELECT * FROM reservations WHERE id = $1", res2["id"])
    assert res2row["state"] == "reserved"  # envoyée : à réconcilier, PAS libérée aveuglément
