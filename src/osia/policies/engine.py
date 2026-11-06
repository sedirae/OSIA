from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import asyncpg

from ..ids import new_id
from ..models import OpKind, PolicyDeny
from .budgets import BudgetManager
from .limits import limits_from_record


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
        async with self.pool.acquire() as conn:
            inv = await conn.fetchrow("SELECT * FROM investigations WHERE id = $1", investigation_id)
            if inv is None:
                return Decision(allowed=False, reason="investigation_inconnue")
            if inv["state"] != "running":
                return Decision(allowed=False, reason=f"investigation_non_active:{inv['state']}")
            limits = limits_from_record(inv)
            if kind == OpKind.SOURCE_REQUEST:
                done = await conn.fetchval(
                    "SELECT COUNT(*) FROM external_ops WHERE investigation_id = $1 AND kind = 'source_request' "
                    "AND state IN ('reserved','in_flight','completed','reconciled')",
                    investigation_id,
                )
                if int(done) >= limits.max_source_requests:
                    return Decision(allowed=False, reason="plafond_requetes_source_atteint")
                timeout = limits.http_timeout_seconds
            else:
                done = await conn.fetchval(
                    "SELECT COUNT(*) FROM external_ops WHERE investigation_id = $1 AND kind = 'ai_call' "
                    "AND state IN ('reserved','in_flight','completed','reconciled')",
                    investigation_id,
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
            await self.pool.execute(
                "UPDATE external_ops SET state = 'reserved', reservation_id = $2, updated_at = now() WHERE id = $1",
                op["id"],
                reservation_id,
            )
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

    async def mark_in_flight(self, op_id: str) -> None:
        await self.pool.execute(
            "UPDATE external_ops SET state = 'in_flight', updated_at = now() WHERE id = $1 AND state IN ('authorized','reserved')",
            op_id,
        )

    async def complete_op(self, op_id: str, result: dict, actual_cents: Optional[int] = None) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM external_ops WHERE id = $1 FOR UPDATE", op_id)
                if row is None:
                    return
                await conn.execute(
                    "UPDATE external_ops SET state = 'completed', result = $2::jsonb, updated_at = now() WHERE id = $1",
                    op_id,
                    json.dumps(result, ensure_ascii=False, default=str),
                )
                if row["reservation_id"] and actual_cents is not None:
                    await self.budgets.consume(row["reservation_id"], actual_cents)

    async def fail_op(self, op_id: str, error: str) -> None:
        await self._fail_op(op_id, error)

    async def mark_uncertain(self, op_id: str) -> None:
        """Appel interrompu dont le résultat/facturation est inconnu (OSIA-I-09) : jamais relancé aveuglément."""
        await self.pool.execute(
            "UPDATE external_ops SET state = 'uncertain', updated_at = now() "
            "WHERE id = $1 AND state IN ('reserved','in_flight')",
            op_id,
        )
