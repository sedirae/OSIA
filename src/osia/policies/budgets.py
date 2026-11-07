from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from ..ids import new_id
from ..models import BudgetView, PolicyDeny


def _period(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


class BudgetManager:
    """Registre financier (CON-04) : plafonds hiérarchiques et réservations transactionnelles (T8.4, OSIA-I-02).

    Montants en centimes d'euro (entiers). Période mensuelle calendaire UTC par défaut.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def _paid_enabled(self, conn: asyncpg.Connection) -> bool:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = 'paid_calls_enabled'")
        value = row["value"] if row else False
        if isinstance(value, str):
            value = json.loads(value)
        return bool(value)

    async def _global_cap(self, conn: asyncpg.Connection) -> int:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = 'global_monthly_cap_cents'")
        value = row["value"] if row else 500
        if isinstance(value, str):
            value = json.loads(value)
        return int(value)

    async def _caps(
        self,
        conn: asyncpg.Connection,
        investigation_id: str,
        branch_id: Optional[str],
    ) -> dict[str, int]:
        inv = await conn.fetchrow("SELECT effective_limits FROM investigations WHERE id = $1", investigation_id)
        if inv is None:
            raise PolicyDeny("investigation_inconnue", "policy")
        limits = inv["effective_limits"]
        if isinstance(limits, str):
            limits = json.loads(limits)
        inv_cap = int(limits["max_cost_cents"])
        caps = {"investigation": inv_cap}
        if branch_id:
            br = await conn.fetchrow("SELECT effective_limits FROM branches WHERE id = $1", branch_id)
            if br is not None:
                br_limits = br["effective_limits"]
                if isinstance(br_limits, str):
                    br_limits = json.loads(br_limits)
                caps["branch"] = min(inv_cap, int(br_limits["max_cost_cents"]))
        if await self._paid_enabled(conn):
            caps["global_month"] = await self._global_cap(conn)
        else:
            caps["global_month"] = 0
        return caps

    async def _used(
        self,
        conn: asyncpg.Connection,
        investigation_id: str,
        branch_id: Optional[str],
        provider: Optional[str],
        model: Optional[str],
        period: str,
    ) -> dict[str, int]:
        used: dict[str, int] = {}
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM ledger "
            "WHERE investigation_id = $1 AND kind = 'consumed'",
            investigation_id,
        )
        used["investigation"] = int(row["total"])
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM reservations "
            "WHERE investigation_id = $1 AND state = 'reserved'",
            investigation_id,
        )
        used["investigation"] += int(row["total"])
        if branch_id:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(r.amount_cents), 0) AS total FROM reservations r "
                "WHERE r.branch_id = $1 AND r.state = 'reserved'",
                branch_id,
            )
            branch_used = int(row["total"])
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(l.amount_cents), 0) AS total FROM ledger l "
                "JOIN reservations r ON r.id = l.reservation_id "
                "WHERE r.branch_id = $1 AND l.kind = 'consumed'",
                branch_id,
            )
            used["branch"] = branch_used + int(row["total"])
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM ledger WHERE kind = 'consumed' AND period = $1",
            period,
        )
        global_used = int(row["total"])
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM reservations "
            "WHERE state = 'reserved' AND to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM') = $1",
            period,
        )
        used["global_month"] = global_used + int(row["total"])
        return used

    async def reserve(
        self,
        *,
        idempotency_key: str,
        investigation_id: str,
        op_id: str,
        amount_cents: int,
        branch_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> asyncpg.Record:
        """Réservation transactionnelle (T8.4 étape 3) : idempotente, atomique avec le verrou de l'opération.

        Le contrôle de plafond est sérialisé : verrou de ligne sur l'investigation (et la
        branche), verrou consultatif transactionnel global pour le plafond mensuel —
        deux réservations concurrentes ne peuvent pas dépasser un plafond.
        """
        period = _period(datetime.now(timezone.utc))
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT * FROM reservations WHERE idempotency_key = $1", idempotency_key
                )
                if existing is not None:
                    return existing
                locked = await conn.fetchrow(
                    "SELECT id FROM investigations WHERE id = $1 FOR UPDATE", investigation_id
                )
                if locked is None:
                    raise PolicyDeny("investigation_inconnue", "policy")
                if branch_id:
                    locked_branch = await conn.fetchrow(
                        "SELECT id FROM branches WHERE id = $1 AND investigation_id = $2 FOR UPDATE",
                        branch_id,
                        investigation_id,
                    )
                    if locked_branch is None:
                        raise PolicyDeny("branche_inconnue", "ledger")
                if await self._paid_enabled(conn):
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('osia:budget:global_month'))")
                caps = await self._caps(conn, investigation_id, branch_id)
                used = await self._used(conn, investigation_id, branch_id, provider, model, period)
                for scope, cap in caps.items():
                    if used.get(scope, 0) + amount_cents > cap:
                        raise PolicyDeny(f"plafond_{scope}_depasse", scope)
                reservation = await conn.fetchrow(
                    "INSERT INTO reservations (id, idempotency_key, investigation_id, branch_id, provider, model, op_id, amount_cents) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *",
                    new_id("res"),
                    idempotency_key,
                    investigation_id,
                    branch_id,
                    provider,
                    model,
                    op_id,
                    amount_cents,
                )
                await conn.execute(
                    "INSERT INTO ledger (investigation_id, reservation_id, kind, amount_cents, period, note) "
                    "VALUES ($1, $2, 'reserved', $3, $4, $5)",
                    investigation_id,
                    reservation["id"],
                    amount_cents,
                    period,
                    "réservation transactionnelle",
                )
                return reservation

    async def consume(self, reservation_id: str, actual_cents: int) -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE reservations SET state = 'consumed', updated_at = now() "
                    "WHERE id = $1 AND state = 'reserved' RETURNING *",
                    reservation_id,
                )
                if row is None:
                    raise PolicyDeny("reservation_non_reservee", "ledger")
                period = _period(row["created_at"])
                await conn.execute(
                    "INSERT INTO ledger (investigation_id, reservation_id, kind, amount_cents, period, note) "
                    "VALUES ($1, $2, 'consumed', $3, $4, $5)",
                    row["investigation_id"],
                    reservation_id,
                    actual_cents,
                    period,
                    "consommation réelle constatée",
                )
                if actual_cents != row["amount_cents"]:
                    await conn.execute(
                        "INSERT INTO ledger (investigation_id, reservation_id, kind, amount_cents, period, note) "
                        "VALUES ($1, $2, 'reconciled', $3, $4, $5)",
                        row["investigation_id"],
                        reservation_id,
                        actual_cents - row["amount_cents"],
                        period,
                        "écart réservation/facturation visible (T8.4)",
                    )
                return row

    async def release(self, reservation_id: str, *, note: str = "enveloppe libérée") -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE reservations SET state = 'released', updated_at = now() "
                    "WHERE id = $1 AND state = 'reserved' RETURNING *",
                    reservation_id,
                )
                if row is None:
                    raise PolicyDeny("reservation_non_reservee", "ledger")
                await conn.execute(
                    "INSERT INTO ledger (investigation_id, reservation_id, kind, amount_cents, period, note) "
                    "VALUES ($1, $2, 'released', $3, $4, $5)",
                    row["investigation_id"],
                    reservation_id,
                    -row["amount_cents"],
                    _period(row["created_at"]),
                    note,
                )
                return row

    async def budget_view(self, investigation_id: str) -> BudgetView:
        period = _period(datetime.now(timezone.utc))
        async with self.pool.acquire() as conn:
            caps = await self._caps(conn, investigation_id, None)
            used = await self._used(conn, investigation_id, None, None, None, period)
        reserved = int(
            await self.pool.fetchval(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM reservations WHERE investigation_id = $1 AND state = 'reserved'",
                investigation_id,
            ) or 0
        )
        consumed = int(
            await self.pool.fetchval(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM ledger WHERE investigation_id = $1 AND kind = 'consumed'",
                investigation_id,
            ) or 0
        )
        available = min(cap - used.get(scope, 0) for scope, cap in caps.items())
        # D3 §5.4 : avertissements à l'approche d'un plafond (seuil 80 %)
        warnings: list[str] = []
        for scope, cap in caps.items():
            u = used.get(scope, 0)
            if cap <= 0:
                if scope == "global_month":
                    warnings.append("appels payants désactivés : plafond global mensuel à 0 (V1.4, budget 0 € au premier démarrage)")
                continue
            pct = round(100 * u / cap)
            if pct >= 80:
                warnings.append(f"plafond {scope} atteint à {pct} % ({u}/{cap} centimes)")
        return BudgetView(
            estimated_cents=0,
            reserved_cents=max(reserved, 0),
            consumed_cents=consumed,
            available_cents=max(available, 0),
            caps=caps,
            warnings=warnings,
        )
