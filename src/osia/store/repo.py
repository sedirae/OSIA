from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..ids import new_id
from ..models import Event


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


_JSON_FIELDS = {"hints", "effective_limits", "payload", "result", "data", "proof_ids", "value"}


def _norm_row(row):
    if row is None:
        return None
    data = dict(row)
    for key in _JSON_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value[:1] in ("{", "["):
            data[key] = json.loads(value)
    return data


def _period(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


class Repo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def _fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        return _norm_row(await self.pool.fetchrow(query, *args))

    async def _fetch(self, query: str, *args) -> list:
        return [_norm_row(r) for r in await self.pool.fetch(query, *args)]

    async def get_setting(self, key: str, default: Any = None) -> Any:
        row = await self._fetchrow("SELECT value FROM settings WHERE key = $1", key)
        if not row:
            return default
        value = row["value"]
        if isinstance(value, str):
            # colonne jsonb lue en texte brut par asyncpg : décoder le scalaire JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    async def set_setting(self, key: str, value: Any) -> None:
        await self.pool.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            key,
            _json(value),
        )

    async def get_profile(self, profile_id: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM profiles WHERE id = $1", profile_id)

    async def list_profiles(self) -> list[asyncpg.Record]:
        return await self._fetch("SELECT * FROM profiles ORDER BY id")

    async def create_profile(self, *, profile_id: str, name: str, limits: dict[str, Any], is_default: bool = False) -> asyncpg.Record:
        """CON-13 / D3 §5.3 : profil personnalisé enregistrable. Bornes validées par le CHECK SQL
        (rebonds 1–10, etc.) ; un seul profil par défaut (les autres sont désactivés)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if is_default:
                    await conn.execute("UPDATE profiles SET is_default = false")
                return _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO profiles (id, name, max_rebonds, max_source_requests, max_ai_calls, max_duration_seconds, max_cost_cents, is_default) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *",
                        profile_id,
                        name,
                        int(limits["max_rebonds"]),
                        int(limits["max_source_requests"]),
                        int(limits["max_ai_calls"]),
                        int(limits["max_duration_seconds"]),
                        int(limits["max_cost_cents"]),
                        is_default,
                    )
                )

    # ---------- Cache technique des requêtes source (CON-13, V1.4 : TTL 24 h par défaut) ----------

    @staticmethod
    def cache_key(connector_id: str, query: str) -> str:
        import hashlib

        return hashlib.sha256(f"{connector_id}\0{query.strip()}".encode("utf-8")).hexdigest()

    async def cache_get(self, connector_id: str, query: str) -> Optional[dict[str, Any]]:
        """Résultat encore valide (B-ACC-06) ou None. La fraîcheur est tracée (D4 §6.2)."""
        row = await self._fetchrow(
            "SELECT result, fetched_at, expires_at FROM source_cache WHERE connector_id = $1 AND query_hash = $2 AND expires_at > now()",
            connector_id,
            self.cache_key(connector_id, query),
        )
        if row is None:
            return None
        result = row["result"]
        if isinstance(result, str):
            result = json.loads(result)
        return {**result, "cached": True, "fetched_at": row["fetched_at"].isoformat(), "expires_at": row["expires_at"].isoformat()}

    async def cache_set(self, connector_id: str, query: str, result: dict[str, Any], ttl_hours: int) -> None:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        await self.pool.execute(
            "INSERT INTO source_cache (id, connector_id, query_hash, result, fetched_at, expires_at) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6) "
            "ON CONFLICT (connector_id, query_hash) DO UPDATE SET result = EXCLUDED.result, fetched_at = EXCLUDED.fetched_at, expires_at = EXCLUDED.expires_at",
            new_id("cache"),
            connector_id,
            self.cache_key(connector_id, query),
            _json(result),
            now,
            now + timedelta(hours=max(1, int(ttl_hours))),
        )

    async def cache_purge_expired(self) -> int:
        """Purge du cache technique expiré (D4 §6.1.B : expiration automatique possible car le
        cache n'est pas nécessaire à la traçabilité des investigations conservées)."""
        status = await self.pool.execute("DELETE FROM source_cache WHERE expires_at <= now()")
        return int(status.split()[-1]) if status else 0

    async def cache_expired_stats(self) -> dict[str, int]:
        """CON-18 : compteur (dry-run) des entrées de cache expirées et de leurs octets."""
        row = await self.pool.fetchrow(
            "SELECT COUNT(*) AS n, COALESCE(SUM(pg_column_size(result)), 0) AS bytes FROM source_cache WHERE expires_at <= now()"
        )
        return {"entries": int(row["n"]), "bytes": int(row["bytes"])}

    async def insert_investigation(
        self,
        *,
        title: str,
        objective: Optional[str],
        hints: list[str],
        profile_id: str,
        effective_limits: dict[str, Any],
        idempotency_key: Optional[str],
        state: str = "running",
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO investigations (id, title, objective, hints, profile_id, effective_limits, state, idempotency_key) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, $7, $8) RETURNING *",
            new_id("inv"),
            title,
            objective,
            _json(hints),
            profile_id,
            _json(effective_limits),
            state,
            idempotency_key,
        )

    async def find_investigation_by_key(self, idempotency_key: str) -> asyncpg.Record | None:
        return await self._fetchrow(
            "SELECT * FROM investigations WHERE idempotency_key = $1", idempotency_key
        )

    async def get_investigation(self, investigation_id: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM investigations WHERE id = $1", investigation_id)

    async def list_investigations(self) -> list[asyncpg.Record]:
        return await self._fetch("SELECT * FROM investigations ORDER BY created_at DESC")

    async def set_investigation_state(
        self, investigation_id: str, state: str, stop_reason: Optional[str] = None
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "UPDATE investigations SET state = $2, stop_reason = $3, updated_at = now() "
            "WHERE id = $1 RETURNING *",
            investigation_id,
            state,
            stop_reason,
        )

    async def insert_branch(
        self,
        *,
        investigation_id: str,
        objective: str,
        effective_limits: dict[str, Any],
        parent_branch_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        state: str = "running",
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO branches (id, investigation_id, parent_branch_id, objective, effective_limits, state, idempotency_key) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7) RETURNING *",
            new_id("br"),
            investigation_id,
            parent_branch_id,
            objective,
            _json(effective_limits),
            state,
            idempotency_key,
        )

    async def find_branch_by_key(self, idempotency_key: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM branches WHERE idempotency_key = $1", idempotency_key)

    async def get_branch(self, branch_id: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM branches WHERE id = $1", branch_id)

    async def list_branches(self, investigation_id: str) -> list[asyncpg.Record]:
        return await self._fetch(
            "SELECT * FROM branches WHERE investigation_id = $1 ORDER BY created_at", investigation_id
        )

    async def set_branch_state(
        self, branch_id: str, state: str, stop_reason: Optional[str] = None
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "UPDATE branches SET state = $2, stop_reason = $3, updated_at = now() WHERE id = $1 RETURNING *",
            branch_id,
            state,
            stop_reason,
        )

    async def insert_task(
        self,
        *,
        investigation_id: str,
        kind: str,
        payload: dict[str, Any],
        branch_id: Optional[str] = None,
        depth: int = 0,
        priority: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO tasks (id, investigation_id, branch_id, kind, payload, depth, priority, idempotency_key) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8) RETURNING *",
            new_id("task"),
            investigation_id,
            branch_id,
            kind,
            _json(payload),
            depth,
            priority,
            idempotency_key,
        )

    async def get_task(self, task_id: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)

    async def list_tasks(self, investigation_id: str) -> list[asyncpg.Record]:
        return await self._fetch(
            "SELECT * FROM tasks WHERE investigation_id = $1 ORDER BY created_at", investigation_id
        )

    async def claim_next_task(self) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return _norm_row(await conn.fetchrow(
                    "UPDATE tasks SET state = 'claimed', started_at = now(), updated_at = now(), attempts = attempts + 1 "
                    "WHERE id = (SELECT t.id FROM tasks t JOIN investigations i ON i.id = t.investigation_id "
                    "WHERE t.state = 'queued' AND t.not_before <= now() AND i.state = 'running' "
                    "ORDER BY t.priority DESC, t.created_at LIMIT 1 FOR UPDATE OF t SKIP LOCKED) "
                    "RETURNING *"
                ))

    async def set_task_state(
        self,
        task_id: str,
        state: str,
        error: Optional[str] = None,
        finished: bool = False,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "UPDATE tasks SET state = $2::text, error = COALESCE($4::text, error), "
            "updated_at = now(), finished_at = CASE WHEN $3::boolean THEN now() ELSE finished_at END, "
            "started_at = COALESCE(started_at, now()) "
            "WHERE id = $1::text RETURNING *",
            task_id,
            state,
            finished,
            error,
        )

    async def insert_op(
        self,
        *,
        investigation_id: str,
        kind: str,
        target: str,
        is_paid: bool = False,
        cost_estimated_cents: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO external_ops (id, task_id, investigation_id, kind, target, is_paid, cost_estimated_cents) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            new_id("op"),
            task_id,
            investigation_id,
            kind,
            target,
            is_paid,
            cost_estimated_cents,
        )

    async def get_op(self, op_id: str) -> asyncpg.Record | None:
        return await self._fetchrow("SELECT * FROM external_ops WHERE id = $1", op_id)

    async def set_op_state(
        self,
        op_id: str,
        state: str,
        *,
        reservation_id: Optional[str] = None,
        result: Any = None,
        error: Optional[str] = None,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "UPDATE external_ops SET state = $2::text, reservation_id = COALESCE($3::text, reservation_id), "
            "result = COALESCE($4::jsonb, result), error = COALESCE($5::text, error), updated_at = now() "
            "WHERE id = $1::text RETURNING *",
            op_id,
            state,
            reservation_id,
            _json(result) if result is not None else None,
            error,
        )

    async def list_ops(self, investigation_id: str) -> list[asyncpg.Record]:
        return await self._fetch(
            "SELECT * FROM external_ops WHERE investigation_id = $1 ORDER BY created_at", investigation_id
        )

    async def append_event(
        self,
        *,
        type: str,
        investigation_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        payload: dict[str, Any] | None = None,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO events (investigation_id, branch_id, type, payload) VALUES ($1, $2, $3, $4::jsonb) RETURNING *",
            investigation_id,
            branch_id,
            type,
            _json(payload or {}),
        )

    async def list_events(
        self, investigation_id: str, after_id: int = 0, limit: int = 500
    ) -> list[Event]:
        rows = await self._fetch(
            "SELECT * FROM events WHERE investigation_id = $1 AND id > $2 ORDER BY id LIMIT $3",
            investigation_id,
            after_id,
            limit,
        )
        return [Event(id=r["id"], investigation_id=r["investigation_id"], branch_id=r["branch_id"], type=r["type"], payload=r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"]), created_at=r["created_at"]) for r in rows]

    async def insert_proof_file(self, *, sha256: str, path: str, size_bytes: int) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO proof_files (sha256, path, size_bytes) VALUES ($1, $2, $3) "
            "ON CONFLICT (sha256) DO NOTHING RETURNING *",
            sha256,
            path,
            size_bytes,
        )

    async def insert_proof_ref(
        self,
        *,
        investigation_id: str,
        sha256: str,
        source_url: Optional[str] = None,
        media_type: Optional[str] = None,
        label: Optional[str] = None,
        connector_id: Optional[str] = None,
    ) -> asyncpg.Record:
        return await self._fetchrow(
            "INSERT INTO proof_refs (id, investigation_id, proof_sha256, source_url, media_type, label, connector_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            new_id("proof"),
            investigation_id,
            sha256,
            source_url,
            media_type,
            label,
            connector_id,
        )

    async def list_proof_refs(self, investigation_id: str) -> list[asyncpg.Record]:
        return await self._fetch(
            "SELECT pr.*, pf.path, pf.size_bytes FROM proof_refs pr "
            "JOIN proof_files pf ON pf.sha256 = pr.proof_sha256 "
            "WHERE pr.investigation_id = $1 ORDER BY pr.fetched_at",
            investigation_id,
        )

    async def list_proof_files(self) -> list[asyncpg.Record]:
        return await self._fetch("SELECT * FROM proof_files")
