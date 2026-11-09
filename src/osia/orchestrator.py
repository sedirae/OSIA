from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

import asyncpg

from .events import EventBus
from .ids import new_id
from .models import (
    CreateBranchRequest,
    CreateInvestigationRequest,
    InvestigationState,
    PolicyDeny,
    StopReason,
)
from .policies.limits import limits_from_profile_row, limits_from_record
from .store.repo import Repo, _norm_row

if TYPE_CHECKING:
    from .policies.budgets import BudgetManager


class Orchestrator:
    """Machine à états des investigations et branches (CON-03, T3.4, T4.3, T4.6).

    L'IA propose (via tâches), le moteur autorise (PolicyEngine) ; l'arrêt sur objectif
    étayé est automatique, toute prolongation exige une branche avec validation explicite.
    """

    def __init__(self, pool: asyncpg.Pool, repo: Repo, bus: EventBus, budgets: "BudgetManager | None" = None):
        self.pool = pool
        self.repo = repo
        self.bus = bus
        self.budgets = budgets

    async def start_investigation(self, req: CreateInvestigationRequest) -> asyncpg.Record:
        if req.idempotency_key:
            existing = await self.repo.find_investigation_by_key(req.idempotency_key)
            if existing is not None:
                return existing
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                profile = await conn.fetchrow("SELECT * FROM profiles WHERE id = $1", req.profile_id)
                if profile is None:
                    raise PolicyDeny(f"profil_inconnu:{req.profile_id}", "policy")
                limits = limits_from_profile_row(profile, req.limits)
                inv = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO investigations (id, title, objective, hints, profile_id, effective_limits, state, idempotency_key) "
                        "VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, 'running', $7) RETURNING *",
                        new_id("inv"),
                        req.title,
                        req.objective,
                        json.dumps(req.hints, ensure_ascii=False),
                        req.profile_id,
                        json.dumps(limits.model_dump(), ensure_ascii=False),
                        req.idempotency_key,
                    )
                )
                branch = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO branches (id, investigation_id, objective, effective_limits, state, depth) "
                        "VALUES ($1, $2, $3, $4::jsonb, 'running', 0) RETURNING *",
                        new_id("br"),
                        inv["id"],
                        req.objective or req.title,
                        json.dumps(limits.model_dump(), ensure_ascii=False),
                    )
                )
                await conn.execute(
                    "INSERT INTO tasks (id, investigation_id, branch_id, kind, payload, depth, priority) "
                    "VALUES ($1, $2, $3, 'plan', $4::jsonb, 0, 100)",
                    new_id("task"),
                    inv["id"],
                    branch["id"],
                    json.dumps({"objective": inv["objective"], "hints": req.hints}, ensure_ascii=False),
                )
        await self.bus.emit(
            type="investigation.created",
            investigation_id=inv["id"],
            payload={"title": inv["title"], "profile": inv["profile_id"]},
        )
        await self.bus.emit(
            type="investigation.started",
            investigation_id=inv["id"],
            branch_id=branch["id"],
            payload={"limits": limits.model_dump()},
        )
        return inv

    async def create_branch(self, investigation_id: str, req: CreateBranchRequest) -> asyncpg.Record:
        """Branche d'approfondissement : jamais lancée sans validation explicite (T4.3, V1.1),
        et ses plafonds ne peuvent dépasser ceux de l'investigation parente (D3.5)."""
        if req.idempotency_key:
            existing = await self.repo.find_branch_by_key(req.idempotency_key)
            if existing is not None:
                return existing
        if not req.explicit_acceptance:
            raise PolicyDeny("validation_explicite_requise", "branche")
        inv = await self.repo.get_investigation(investigation_id)
        if inv is None:
            raise PolicyDeny("investigation_inconnue", "branche")
        # F08 : une branche explicite sur une investigation arrêtée la RÉACTIVE (c'est la
        # nouvelle autorisation : explicit_acceptance requis, plafonds <= parent). Sur une
        # investigation suspendue, la reprise explicite (resume) reste requise.
        if inv["state"] not in ("running", "stopped"):
            raise PolicyDeny(f"reprise_requise:{inv['state']}", "branche")
        inv_limits = limits_from_record(inv)
        profile = await self.repo.get_profile(inv["profile_id"])
        if profile is None:
            raise PolicyDeny(f"profil_inconnu:{inv['profile_id']}", "branche")
        # CON-13 / D3 §5.4 : une demande de branche au-dessus du plafond de l'investigation est
        # refusée explicitement (jamais clampée silencieusement vers le haut).
        if req.limits:
            for field in ("max_rebonds", "max_source_requests", "max_ai_calls", "max_duration_seconds", "max_cost_cents"):
                demanded = req.limits.get(field)
                if (
                    isinstance(demanded, int)
                    and not isinstance(demanded, bool)
                    and demanded > getattr(inv_limits, field)
                ):
                    raise PolicyDeny(f"plafond_branche_superieur:{field}", "branche")
        branch_limits = limits_from_profile_row(profile, req.limits)
        for field in ("max_rebonds", "max_source_requests", "max_ai_calls", "max_duration_seconds", "max_cost_cents"):
            if getattr(branch_limits, field) > getattr(inv_limits, field):
                raise PolicyDeny(f"plafond_branche_superieur:{field}", "branche")
        depth = 0
        if req.parent_branch_id:
            parent = await self.repo.get_branch(req.parent_branch_id)
            if parent is None or parent["investigation_id"] != investigation_id:
                raise PolicyDeny("branche_parente_inconnue_ou_etrangere", "branche")
            depth = int(parent["depth"]) + 1
            if depth > 10:
                raise PolicyDeny("profondeur_max_atteinte", "branche")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # P2-1 (audit PR #21) : l'état est relu SOUS VERROU dans la transaction —
                # un stop/resume concurrent entre le read initial et la transaction ne peut
                # plus produire une branche créée sans réactivation (qui ne s'exécuterait jamais).
                inv_locked = await conn.fetchrow(
                    "SELECT * FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                if inv_locked is None:
                    raise PolicyDeny("investigation_inconnue", "branche")
                if inv_locked["state"] not in ("running", "stopped"):
                    raise PolicyDeny(f"reprise_requise:{inv_locked['state']}", "branche")
                reactivated = inv_locked["state"] == "stopped"
                if reactivated:
                    # F08 : la branche explicite autonome réactive l'investigation arrêtée
                    # (les anciennes branches restent arrêtées ; seules les tâches de la
                    # nouvelle branche seront exécutées).
                    await conn.execute(
                        "UPDATE investigations SET state = 'running', stop_reason = NULL, updated_at = now() WHERE id = $1",
                        investigation_id,
                    )
                branch = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO branches (id, investigation_id, parent_branch_id, objective, effective_limits, state, depth, idempotency_key) "
                        "VALUES ($1, $2, $3, $4, $5::jsonb, 'running', $6, $7) RETURNING *",
                        new_id("br"),
                        investigation_id,
                        req.parent_branch_id,
                        req.objective,
                        json.dumps(branch_limits.model_dump(), ensure_ascii=False),
                        depth,
                        req.idempotency_key,
                    )
                )
                await conn.execute(
                    "INSERT INTO tasks (id, investigation_id, branch_id, kind, payload, depth, priority) "
                    "VALUES ($1, $2, $3, 'plan', $4::jsonb, 0, 100)",
                    new_id("task"),
                    investigation_id,
                    branch["id"],
                    json.dumps({"objective": req.objective}, ensure_ascii=False),
                )
        if reactivated:
            await self.bus.emit(
                type="investigation.reactivated",
                investigation_id=investigation_id,
                payload={"reason": "branche_explicite", "branch_id": branch["id"]},
            )
        await self.bus.emit(
            type="branch.created",
            investigation_id=investigation_id,
            branch_id=branch["id"],
            payload={"objective": req.objective, "limits": branch_limits.model_dump()},
        )
        return branch

    async def _stop_in_conn(self, conn, investigation_id: str, reason: StopReason) -> tuple[bool, asyncpg.Record]:
        """Corps de stop() exécuté DANS une transaction appelante (verrou investigation pris par
        l'appelant si besoin) : transition + branches + tâches + opérations externes (F04)."""
        inv = _norm_row(
            await conn.fetchrow(
                "UPDATE investigations SET state = 'stopped', stop_reason = $2, updated_at = now() "
                "WHERE id = $1 AND state IN ('running','suspended') RETURNING *",
                investigation_id,
                reason.value,
            )
        )
        matched = inv is not None
        if inv is None:
            inv = await conn.fetchrow("SELECT * FROM investigations WHERE id = $1", investigation_id)
        await conn.execute(
            "UPDATE branches SET state = 'stopped', stop_reason = $2, updated_at = now() "
            "WHERE investigation_id = $1 AND state IN ('running','suspended')",
            investigation_id,
            reason.value,
        )
        await conn.execute(
            "UPDATE tasks SET state = 'cancelled', updated_at = now(), finished_at = now() "
            "WHERE investigation_id = $1 AND state IN ('queued','claimed')",
            investigation_id,
        )
        # F04 : distinguer jamais-envoyé (authorized/reserved -> cancelled + enveloppe
        # libérée) et envoyé (in_flight -> uncertain, à réconcilier, jamais relancé).
        await conn.execute(
            "UPDATE external_ops SET state = 'cancelled', updated_at = now() "
            "WHERE investigation_id = $1 AND state IN ('authorized','reserved')",
            investigation_id,
        )
        await conn.execute(
            "UPDATE external_ops SET state = 'uncertain', updated_at = now() "
            "WHERE investigation_id = $1 AND state = 'in_flight'",
            investigation_id,
        )
        return matched, inv

    async def stop(self, investigation_id: str, reason: StopReason) -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                matched, inv = await self._stop_in_conn(conn, investigation_id, reason)
                if self.budgets is not None:
                    # Réserve audit PR#19 P3-6 : libération DANS la transaction — un crash
                    # entre les deux ne laisse pas de réservations orphelines.
                    await self.budgets.release_ops_reservations_in_conn(
                        conn, investigation_id, note=f"arrêt ({reason.value}) : opérations jamais envoyées"
                    )
        if matched:
            await self.bus.emit(
                type="investigation.stopped",
                investigation_id=investigation_id,
                payload={"reason": reason.value},
            )
        return inv

    async def suspend(self, investigation_id: str) -> asyncpg.Record:
        # F08 : une pause n'est PAS une annulation définitive — les tâches en file/en cours
        # passent 'interrupted' (re-mises en file par resume()), distinct de 'cancelled' (stop).
        # P3-6 (audit PR#19) : état + libération des réservations dans UNE transaction —
        # aucun état intermédiaire observable (crash = rollback complet).
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inv = _norm_row(
                    await conn.fetchrow(
                        "UPDATE investigations SET state = $2, stop_reason = NULL, updated_at = now() WHERE id = $1 RETURNING *",
                        investigation_id,
                        InvestigationState.SUSPENDED.value,
                    )
                )
                await conn.execute(
                    "UPDATE tasks SET state = 'interrupted', updated_at = now() "
                    "WHERE investigation_id = $1 AND state IN ('queued','claimed','running')",
                    investigation_id,
                )
                await conn.execute(
                    "UPDATE branches SET state = 'suspended', updated_at = now() "
                    "WHERE investigation_id = $1 AND state = 'running'",
                    investigation_id,
                )
                # F04 : idem stop — jamais-envoyé libéré, envoyé passé en uncertain
                await conn.execute(
                    "UPDATE external_ops SET state = 'cancelled', updated_at = now() "
                    "WHERE investigation_id = $1 AND state IN ('authorized','reserved')",
                    investigation_id,
                )
                await conn.execute(
                    "UPDATE external_ops SET state = 'uncertain', updated_at = now() "
                    "WHERE investigation_id = $1 AND state = 'in_flight'",
                    investigation_id,
                )
                if self.budgets is not None:
                    await self.budgets.release_ops_reservations_in_conn(conn, investigation_id, note="suspension : opérations jamais envoyées")
        await self.bus.emit(type="investigation.suspended", investigation_id=investigation_id, payload={})
        return inv

    async def resume(self, investigation_id: str) -> asyncpg.Record:
        """Reprise : vérifie l'état, ne relance jamais aveuglément les opérations incertaines (D7.4, OSIA-I-09)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inv = await conn.fetchrow(
                    "SELECT * FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                if inv is None:
                    raise PolicyDeny("investigation_inconnue", "reprise")
                if inv["state"] != InvestigationState.SUSPENDED.value:
                    raise PolicyDeny(f"reprise_impossible:{inv['state']}", "reprise")
                uncertain = await conn.fetchval(
                    "SELECT COUNT(*) FROM external_ops WHERE investigation_id = $1 AND state = 'uncertain'",
                    investigation_id,
                )
                if uncertain:
                    raise PolicyDeny(
                        f"reconciliation_requise:{uncertain} operation(s) incertaine(s) a reconcilier avant reprise",
                        "reprise",
                    )
                inv = _norm_row(
                    await conn.fetchrow(
                        "UPDATE investigations SET state = 'running', stop_reason = NULL, updated_at = now() "
                        "WHERE id = $1 RETURNING *",
                        investigation_id,
                    )
                )
                await conn.execute(
                    "UPDATE branches SET state = 'running', stop_reason = NULL, updated_at = now() "
                    "WHERE investigation_id = $1 AND state = 'suspended'",
                    investigation_id,
                )
                await conn.execute(
                    "UPDATE tasks SET state = 'queued', updated_at = now() "
                    "WHERE investigation_id = $1 AND state = 'interrupted'",
                    investigation_id,
                )
        await self.bus.emit(type="investigation.resumed", investigation_id=investigation_id, payload={})
        return inv

    async def on_policy_deny(self, task: asyncpg.Record, deny: PolicyDeny) -> None:
        reason = deny.reason or ""
        if reason.startswith(("plafond_investigation", "plafond_branch", "plafond_global_month")) or "budget" in reason or "cout_inconnu" in reason:
            await self.stop(task["investigation_id"], StopReason.BUDGET)
        elif reason in ("plafond_requetes_source_atteint", "plafond_appels_ia_atteint"):
            await self.stop(task["investigation_id"], StopReason.SOURCES)

    async def _maybe_terminate_if_exhausted(self, investigation_id: str, note: str = "") -> None:
        """F08 : état terminal explicite — si l'investigation est encore 'running' sans aucune
        tâche exécutable (queued/claimed/running), elle est arrêtée (work_exhausted) au lieu de
        rester 'running' indéfiniment (plan vide, plus de suite, tâches en échec).
        P3-1 (audit PR #21) : comptage ET arrêt dans la MÊME transaction sous verrou de
        l'investigation — une branche créée concurremment ne peut pas voir sa tâche annulée."""
        matched = False
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inv = await conn.fetchrow(
                    "SELECT * FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                if inv is None or inv["state"] != "running":
                    return
                pending = await conn.fetchval(
                    "SELECT COUNT(*) FROM tasks WHERE investigation_id = $1 AND state IN ('queued','claimed','running')",
                    investigation_id,
                )
                if pending:
                    return
                matched, _inv = await self._stop_in_conn(conn, investigation_id, StopReason.EXHAUSTED)
                if self.budgets is not None:
                    # P3-6 (audit PR#19) : libération DANS la transaction du stop.
                    await self.budgets.release_ops_reservations_in_conn(
                        conn, investigation_id, note=f"épuisement ({StopReason.EXHAUSTED.value}) : opérations jamais envoyées"
                    )
        if matched:
            await self.bus.emit(
                type="investigation.stopped",
                investigation_id=investigation_id,
                payload={"reason": StopReason.EXHAUSTED.value},
            )
            await self.bus.emit(
                type="investigation.exhausted",
                investigation_id=investigation_id,
                payload={"note": note},
            )

    async def on_task_succeeded(self, task: asyncpg.Record, result: dict[str, Any]) -> None:
        await self._maybe_terminate_if_exhausted(
            task["investigation_id"], note=f"tâche {task['id']} réussie, aucun travail exécutable restant"
        )

    async def on_task_failed(self, task: asyncpg.Record, error: str) -> None:
        """F08 : idem après un échec — un plan vide ou une chaîne rompue termine l'investigation
        explicitement au lieu de laisser 'running' sans tâche exécutable."""
        await self._maybe_terminate_if_exhausted(
            task["investigation_id"], note=f"tâche {task['id']} en échec ({error}), aucun travail exécutable restant"
        )
