from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from ..ids import new_id
from ..models import LimitSet, OpKind, PolicyDeny
from .budgets import BudgetManager
from .limits import limits_from_record

# États comptés contre les quotas : toute opération admise (y compris 'authorized' pas encore
# réservée) compte ; seules les opérations terminales sans envoi (failed/cancelled) sont exclues.
_COUNTED_OP_STATES = ("authorized", "reserved", "in_flight", "completed", "uncertain", "reconciled")


def _merge_limits_min(a: LimitSet, b: LimitSet) -> LimitSet:
    """Limites effectives = minimum champ par champ (branche ne peut que resserrer, D3 §5.4)."""
    return LimitSet(**{f: min(getattr(a, f), getattr(b, f)) for f in LimitSet.model_fields})


@dataclass
class Decision:
    allowed: bool
    reason: Optional[str] = None
    op_id: Optional[str] = None
    reservation_id: Optional[str] = None
    timeout_seconds: Optional[int] = None


class PolicyEngine:
    """Moteur de politiques indépendant de l'IA (T3.11, OSIA-I-01/02/04).

    Vérifie avant chaque opération externe : état de l'investigation, limites effectives
    (profondeur, compteurs, durée), autorisation de la source, et réservation budgétaire
    transactionnelle pour toute opération payante.
    """

    def __init__(self, pool: asyncpg.Pool, budgets: BudgetManager, authorized_targets: set[str] | None = None):
        self.pool = pool
        self.budgets = budgets
        self.authorized_targets = authorized_targets if authorized_targets is not None else set()

    def allow_target(self, target: str) -> None:
        self.authorized_targets.add(target)

    async def authorize(
        self,
        *,
        investigation_id: str,
        kind: OpKind,
        target: str,
        is_paid: bool,
        cost_estimated_cents: Optional[int],
        branch_id: Optional[str] = None,
        task_id: Optional[str] = None,
        depth: int = 0,
    ) -> Decision:
        # F04 : admission ATOMIQUE — verrou de ligne sur l'investigation (et la branche) dans une
        # transaction : le comptage des quotas et l'insert de l'opération sont sérialisés, deux
        # tâches concurrentes ne peuvent pas passer le même quota.
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inv = await conn.fetchrow(
                    "SELECT * FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                if inv is None:
                    return Decision(allowed=False, reason="investigation_inconnue")
                if inv["state"] != "running":
                    return Decision(allowed=False, reason=f"investigation_non_active:{inv['state']}")
                limits = limits_from_record(inv)
                if branch_id:
                    # F04 : la branche doit exister, appartenir à l'investigation et être active ;
                    # ses limites s'appliquent à TOUTES les opérations (pas seulement payantes).
                    br = await conn.fetchrow(
                        "SELECT * FROM branches WHERE id = $1 AND investigation_id = $2 FOR UPDATE",
                        branch_id,
                        investigation_id,
                    )
                    if br is None:
                        return Decision(allowed=False, reason="branche_inconnue")
                    if br["state"] != "running":
                        return Decision(allowed=False, reason=f"branche_non_active:{br['state']}")
                    limits = _merge_limits_min(limits, limits_from_record(br))
                # F04 : échéance persistante — durée écoulée depuis created_at vs max_duration_seconds
                elapsed = (datetime.now(timezone.utc) - inv["created_at"].astimezone(timezone.utc)).total_seconds()
                if elapsed > limits.max_duration_seconds:
                    return Decision(allowed=False, reason="duree_max_atteinte")
                if kind == OpKind.SOURCE_REQUEST:
                    done = await conn.fetchval(
                        "SELECT COUNT(*) FROM external_ops WHERE investigation_id = $1 AND kind = 'source_request' "
                        "AND state = ANY($2::text[])",
                        investigation_id,
                        list(_COUNTED_OP_STATES),
                    )
                    if int(done) >= limits.max_source_requests:
                        return Decision(allowed=False, reason="plafond_requetes_source_atteint")
                    timeout = limits.http_timeout_seconds
                else:
                    done = await conn.fetchval(
                        "SELECT COUNT(*) FROM external_ops WHERE investigation_id = $1 AND kind = 'ai_call' "
                        "AND state = ANY($2::text[])",
                        investigation_id,
                        list(_COUNTED_OP_STATES),
                    )
                    if int(done) >= limits.max_ai_calls:
                        return Decision(allowed=False, reason="plafond_appels_ia_atteint")
                    timeout = limits.ai_timeout_seconds
                if depth > limits.max_rebonds:
                    return Decision(allowed=False, reason="profondeur_max_atteinte")
                if target not in self.authorized_targets:
                    return Decision(allowed=False, reason="cible_non_autorisee")
                op = await conn.fetchrow(
                    "INSERT INTO external_ops (id, task_id, investigation_id, kind, target, is_paid, cost_estimated_cents, state) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, 'authorized') RETURNING *",
                    new_id("op"),
                    task_id,
                    investigation_id,
                    kind.value,
                    target,
                    is_paid,
                    cost_estimated_cents,
                )
        reservation_id: Optional[str] = None
        if is_paid:
            if cost_estimated_cents is None:
                await self._fail_op(op["id"], "cout_inconnu_bloque")
                return Decision(allowed=False, reason="cout_inconnu_bloque", op_id=op["id"])
            try:
                reservation = await self.budgets.reserve(
                    idempotency_key=f"{op['id']}:reserve",
                    investigation_id=investigation_id,
                    branch_id=branch_id,
                    op_id=op["id"],
                    amount_cents=cost_estimated_cents,
                    provider=target.split(":")[0] if kind == OpKind.AI_CALL else None,
                    model=target.split(":")[1] if kind == OpKind.AI_CALL and ":" in target else None,
                )
            except PolicyDeny as deny:
                await self._fail_op(op["id"], deny.reason)
                return Decision(allowed=False, reason=deny.reason, op_id=op["id"])
            reservation_id = reservation["id"]
            attached = await self.pool.fetchval(
                "UPDATE external_ops SET state = 'reserved', reservation_id = $2, updated_at = now() "
                "WHERE id = $1 AND state = 'authorized' RETURNING id",
                op["id"],
                reservation_id,
            )
            if attached is None:
                await self.budgets.release(reservation_id, note="opération annulée pendant la réservation")
                return Decision(allowed=False, reason="operation_annulee_avant_envoi", op_id=op["id"])
        return Decision(
            allowed=True,
            op_id=op["id"],
            reservation_id=reservation_id,
            timeout_seconds=timeout,
        )

    async def _fail_op(self, op_id: str, reason: str) -> None:
        await self.pool.execute(
            "UPDATE external_ops SET state = 'failed', error = $2, updated_at = now() WHERE id = $1",
            op_id,
            reason,
        )

    async def mark_in_flight(self, op_id: str) -> bool:
        """Transition atomique authorized/reserved -> in_flight. Retourne False si l'opération
        n'est plus envoyable (ex. annulée par un stop entre la revalidation et l'envoi) : dans ce
        cas l'appelant ne doit PAS exécuter l'opération (jamais envoyée -> enveloppe libérée)."""
        row = await self.pool.fetchrow(
            "UPDATE external_ops SET state = 'in_flight', updated_at = now() "
            "WHERE id = $1 AND state IN ('authorized','reserved') RETURNING id",
            op_id,
        )
        return row is not None

    async def complete_op(self, op_id: str, result: dict, actual_cents: Optional[int] = None) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None or row["state"] not in ("in_flight", "reserved"):
                    return  # garde d'état : une op annulée/échouée n'est jamais re-transitionnée
                await conn.execute(
                    "UPDATE external_ops SET state = 'completed', result = $2::jsonb, updated_at = now() WHERE id = $1",
                    op_id,
                    json.dumps(result, ensure_ascii=False, default=str),
                )
                if row["reservation_id"] and actual_cents is not None:
                    await self.budgets.consume_in_conn(conn, row["reservation_id"], actual_cents)

    async def fail_op(self, op_id: str, error: str) -> None:
        await self._fail_op(op_id, error)

    async def reconcile_uncertain(
        self, op_id: str, *, billed: bool, actual_cents: Optional[int] = None
    ) -> asyncpg.Record:
        """Réconciliation explicite d'une op 'uncertain' (AGENTS.md règle 10, D7.4) :
        facturée → consommation réelle au registre ; non facturée → libération de l'enveloppe."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None or row["state"] != "uncertain":
                    raise PolicyDeny("operation_non_incertaine", "reconciliation")
                if billed:
                    amount = actual_cents
                    if amount is None:
                        amount = row["cost_estimated_cents"]
                    if amount is None:
                        raise PolicyDeny("cout_inconnu_bloque", "reconciliation")
                    if row["reservation_id"]:
                        await self.budgets.consume_in_conn(conn, row["reservation_id"], amount)
                elif row["reservation_id"]:
                    await self.budgets.release_in_conn(
                        conn, row["reservation_id"], note="réconciliation : appel non facturé"
                    )
                return await conn.fetchrow(
                    "UPDATE external_ops SET state = 'reconciled', updated_at = now() WHERE id = $1 RETURNING *",
                    op_id,
                )

    async def mark_uncertain(self, op_id: str) -> None:
        """Appel interrompu dont le résultat/facturation est inconnu (OSIA-I-09) : jamais relancé aveuglément."""
        await self.pool.execute(
            "UPDATE external_ops SET state = 'uncertain', updated_at = now() "
            "WHERE id = $1 AND state IN ('reserved','in_flight')",
            op_id,
        )

    async def revalidate(self, op_id: str, *, investigation_id: str) -> Decision:
        """Revalidation ATOMIQUE immédiatement avant l'I/O (F04) : l'opération doit exister dans un
        état envoyable, l'investigation doit être active et l'échéance non dépassée. Si refusée,
        l'appelant ne doit PAS exécuter l'opération (attente de sémaphore incluse)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Même ordre que stop/suspend : investigation puis opération.
                inv = await conn.fetchrow(
                    "SELECT * FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                op = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if op is None:
                    return Decision(allowed=False, reason="operation_inconnue")
                if op["state"] not in ("authorized", "reserved"):
                    return Decision(allowed=False, reason=f"operation_non_envoyable:{op['state']}")
                if inv is None:
                    return Decision(allowed=False, reason="investigation_inconnue")
                if inv["state"] != "running":
                    return Decision(allowed=False, reason=f"investigation_non_active:{inv['state']}")
                limits = limits_from_record(inv)
                elapsed = (datetime.now(timezone.utc) - inv["created_at"].astimezone(timezone.utc)).total_seconds()
                if elapsed > limits.max_duration_seconds:
                    return Decision(allowed=False, reason="duree_max_atteinte")
                return Decision(
                    allowed=True,
                    op_id=op_id,
                    reservation_id=op["reservation_id"],
                    timeout_seconds=limits.ai_timeout_seconds if op["kind"] == "ai_call" else limits.http_timeout_seconds,
                )

    async def cancel_op(self, op_id: str, *, reason: str = "annule_avant_envoi") -> None:
        """Opération JAMAIS envoyée (authorized/reserved) : état 'cancelled' + libération de
        l'enveloppe budgétaire (F04 : distinguer jamais-envoyé [libérable] et envoyé [réconciliation])."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None or row["state"] not in ("authorized", "reserved"):
                    return
                await conn.execute(
                    "UPDATE external_ops SET state = 'cancelled', error = $2, updated_at = now() WHERE id = $1",
                    op_id,
                    reason,
                )
                if row["reservation_id"]:
                    await self.budgets.release_in_conn(conn, row["reservation_id"], note=f"annulation avant envoi ({reason})")

    async def fail_op_billed(self, op_id: str, error: str, *, actual_cents: int) -> None:
        """Opération échouée MAIS envoyée et facturée (ex. sortie IA invalide après l'appel, F03) :
        état 'failed' + consommation RÉELLE constatée au registre (l'estimation n'est jamais
        présentée comme montant constaté)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None or row["state"] not in ("in_flight", "reserved"):
                    return  # garde d'état : une op annulée n'est pas re-transitionnée
                await conn.execute(
                    "UPDATE external_ops SET state = 'failed', error = $2, updated_at = now() WHERE id = $1",
                    op_id,
                    error,
                )
                if row["reservation_id"]:
                    await self.budgets.consume_in_conn(conn, row["reservation_id"], actual_cents)

    async def complete_op_uncertain(self, op_id: str, result: dict) -> None:
        """Appel terminé mais facturation INCONNUE (pas d'usage, F03) : résultat persisté, état
        'uncertain' — la réservation reste à réconcilier explicitement (jamais relancé aveuglément)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None or row["state"] not in ("in_flight", "reserved"):
                    return  # garde d'état : une op annulée/échouée n'est jamais re-transitionnée
                await conn.execute(
                    "UPDATE external_ops SET state = 'uncertain', result = $2::jsonb, updated_at = now() WHERE id = $1",
                    op_id,
                    json.dumps(result, ensure_ascii=False, default=str),
                )
