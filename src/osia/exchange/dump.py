from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

import asyncpg

# Tables exportables d'une investigation, dans l'ordre des dependances FK pour l'import.
# refs : colonnes referencant une autre table (pour le remap d'identifiants en mode "add").
TABLES: dict[str, dict[str, Any]] = {
    "investigations": {
        "cols": ["id", "title", "objective", "hints", "profile_id", "effective_limits", "state", "stop_reason", "idempotency_key", "created_at", "updated_at"],
        "refs": {},
        "pk": "id",
    },
    "branches": {
        "cols": ["id", "investigation_id", "parent_branch_id", "objective", "effective_limits", "state", "stop_reason", "depth", "idempotency_key", "created_at", "updated_at"],
        "refs": {"investigation_id": "investigations", "parent_branch_id": "branches"},
        "pk": "id",
        "deferred": ["parent_branch_id"],
    },
    "proof_files": {
        "cols": ["sha256", "path", "size_bytes", "created_at"],
        "refs": {},
        "pk": "sha256",
        "conflict_ok": True,
    },
    "proof_refs": {
        "cols": ["id", "investigation_id", "proof_sha256", "source_url", "media_type", "label", "fetched_at", "connector_id"],
        "refs": {"investigation_id": "investigations"},
        "pk": "id",
    },
    "entities": {
        "cols": ["id", "investigation_id", "kind", "data", "merged_into", "created_at", "updated_at"],
        "refs": {"investigation_id": "investigations", "merged_into": "entities"},
        "pk": "id",
        "deferred": ["merged_into"],
    },
    "entity_identifiers": {
        "cols": ["id", "investigation_id", "entity_id", "scheme", "value_normalisee", "created_at"],
        "refs": {"investigation_id": "investigations", "entity_id": "entities"},
        "pk": "id",
    },
    "match_proposals": {
        "cols": ["id", "investigation_id", "entity_a", "entity_b", "basis", "justification", "confidence", "status", "decided_by", "created_at", "updated_at"],
        "refs": {"investigation_id": "investigations", "entity_a": "entities", "entity_b": "entities"},
        "pk": "id",
    },
    "relations": {
        "cols": ["id", "investigation_id", "src_id", "dst_id", "type", "status", "data", "created_at", "branch_id", "direction", "valid_from", "valid_to", "proof_ids", "support_level", "human_decision", "match_proposal_id", "updated_at"],
        "refs": {"investigation_id": "investigations", "src_id": "entities", "dst_id": "entities", "branch_id": "branches", "match_proposal_id": "match_proposals"},
        "pk": "id",
    },
    "assertions": {
        "cols": ["id", "investigation_id", "branch_id", "statement", "nature", "support", "human_decision", "proof_ids", "created_at", "support_level", "confidence", "superseded_by", "contradicted_by", "decisive", "updated_at"],
        "refs": {"investigation_id": "investigations", "branch_id": "branches", "superseded_by": "assertions"},
        "pk": "id",
        "deferred": ["superseded_by"],
    },
    "decisions": {
        "cols": ["id", "investigation_id", "assertion_id", "action", "payload", "created_at", "target_type", "target_id", "reverts"],
        "refs": {"investigation_id": "investigations", "assertion_id": "assertions", "reverts": "decisions"},
        "pk": "id",
        "deferred": ["reverts"],
        "target_ref": {"entity": "entities", "relation": "relations", "assertion": "assertions", "match_proposal": "match_proposals"},
    },
    "tasks": {
        "cols": ["id", "investigation_id", "branch_id", "kind", "payload", "state", "priority", "depth", "attempts", "not_before", "idempotency_key", "error", "created_at", "updated_at", "started_at", "finished_at"],
        "refs": {"investigation_id": "investigations", "branch_id": "branches"},
        "pk": "id",
    },
    "external_ops": {
        "cols": ["id", "task_id", "investigation_id", "kind", "target", "is_paid", "cost_estimated_cents", "state", "reservation_id", "result", "error", "created_at", "updated_at"],
        "refs": {"investigation_id": "investigations", "task_id": "tasks"},
        "pk": "id",
    },
    "reservations": {
        "cols": ["id", "idempotency_key", "investigation_id", "branch_id", "provider", "model", "op_id", "amount_cents", "state", "created_at", "updated_at"],
        "refs": {"investigation_id": "investigations", "branch_id": "branches", "op_id": "external_ops"},
        "pk": "id",
    },
    "ledger": {
        "cols": ["id", "investigation_id", "reservation_id", "kind", "amount_cents", "period", "note", "created_at"],
        "refs": {"investigation_id": "investigations", "reservation_id": "reservations"},
        "pk": "id",
        "serial": True,
    },
    "events": {
        "cols": ["id", "investigation_id", "branch_id", "type", "payload", "created_at"],
        "refs": {"investigation_id": "investigations", "branch_id": "branches"},
        "pk": "id",
        "serial": True,
    },
}

IMPORT_ORDER = [
    "investigations", "branches", "proof_files", "proof_refs", "entities", "entity_identifiers",
    "match_proposals", "relations", "assertions", "decisions", "tasks", "external_ops",
    "reservations", "ledger", "events",
]

# Tables facultativement exclues d'un export (T7.4) : donnees techniques/financieres ou binaires.
EXCLUDABLE = {"tasks", "external_ops", "reservations", "ledger", "events"}

JSONB_COLS = {
    "investigations": {"hints", "effective_limits"},
    "branches": {"effective_limits"},
    "entities": {"data"},
    "relations": {"data", "proof_ids"},
    "assertions": {"proof_ids", "confidence", "contradicted_by"},
    "decisions": {"payload"},
    "tasks": {"payload"},
    "external_ops": {"result"},
    "events": {"payload"},
}

# Colonnes de type date (ni timestamp ni jsonb) : iso str -> datetime.date a l'import.
DATE_COLS = {
    "relations": {"valid_from", "valid_to"},
}


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def row_to_dict(row: asyncpg.Record, table: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    jsonb_cols = JSONB_COLS.get(table, set())
    for k in row.keys():
        v = row[k]
        if k in jsonb_cols and isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
        out[k] = jsonable(v)
    return out


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else "null", ensure_ascii=False, default=str)


def _parse_dt(value: Any) -> Any:
    if value is None or isinstance(value, (datetime, date)):
        return value
    return datetime.fromisoformat(str(value))


async def dump_investigation(
    pool: asyncpg.Pool,
    investigation_id: str,
    *,
    branch_ids: Optional[list[str]] = None,
    exclusions: Optional[set[str]] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Extrait toutes les tables liees a une investigation (CON-14 §1.3).

    branch_ids restreint branches/tasks/assertions/relations/events aux branches choisies
    (les entites du graphe restent celles de l'investigation). exclusions retire des tables
    techniques/financieres (T7.4)."""
    exclusions = exclusions or set()
    payload: dict[str, list[dict[str, Any]]] = {}
    async with pool.acquire() as conn:
        for table in IMPORT_ORDER:
            if table in exclusions:
                payload[table] = []
                continue
            if table == "investigations":
                rows = await conn.fetch("SELECT * FROM investigations WHERE id = $1", investigation_id)
            elif table == "proof_files":
                rows = await conn.fetch(
                    "SELECT DISTINCT pf.* FROM proof_files pf JOIN proof_refs pr ON pr.proof_sha256 = pf.sha256 "
                    "WHERE pr.investigation_id = $1 ORDER BY pf.sha256",
                    investigation_id,
                )
            elif branch_ids and table in ("branches",):
                ids = branch_ids
                rows = await conn.fetch(
                    "SELECT * FROM branches WHERE investigation_id = $1 AND id = ANY($2) ORDER BY depth, created_at",
                    investigation_id, ids,
                )
            elif branch_ids and table in ("tasks", "assertions", "relations", "events", "reservations"):
                rows = await conn.fetch(
                    f"SELECT * FROM {table} WHERE investigation_id = $1 AND (branch_id IS NULL OR branch_id = ANY($2)) "
                    "ORDER BY created_at",
                    investigation_id, branch_ids,
                )
            else:
                order = "fetched_at" if table == "proof_refs" else "created_at"
                rows = await conn.fetch(
                    f"SELECT * FROM {table} WHERE investigation_id = $1 ORDER BY {order}", investigation_id
                )
            payload[table] = [row_to_dict(r, table) for r in rows]
    return payload


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def _norm_val(value: Any) -> Any:
    """Normalise une valeur pour comparaison : les dates ISO sont comparees comme datetime
    (to_jsonb PostgreSQL tronque les microsecondes, ex. .08297 vs .082970)."""
    if isinstance(value, str) and _ISO_DATE.match(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, dict):
        return {k: _norm_val(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm_val(v) for v in value]
    return value


async def detect_conflicts(
    conn: asyncpg.Connection,
    payload: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Detecte les collisions d'identifiants et les contenus divergents (T7.6, D5.7.2)."""
    conflicts: list[dict[str, Any]] = []
    for table in IMPORT_ORDER:
        spec = TABLES[table]
        if spec.get("serial"):
            continue
        pk = spec["pk"]
        for row in payload.get(table, []):
            existing = await conn.fetchrow(
                f"SELECT to_jsonb(t) AS j FROM (SELECT * FROM {table} WHERE {pk} = $1) t", row[pk]
            )
            if existing is None:
                continue
            left = json.loads(existing["j"])
            same = all(
                json.dumps(_norm_val(left.get(k)), sort_keys=True, default=str)
                == json.dumps(_norm_val(row.get(k)), sort_keys=True, default=str)
                for k in spec["cols"]
            )
            conflicts.append({"table": table, "id": row[pk], "status": "identical" if same else "divergent"})
    return [c for c in conflicts if c["status"] == "divergent"]


async def import_payload(
    pool: asyncpg.Pool,
    payload: dict[str, list[dict[str, Any]]],
    *,
    mode: str = "add",
    on_conflict: str = "fail",
) -> dict[str, Any]:
    """Importe un payload d'archive dans une transaction unique (T7.6, D5.7.5).

    mode "add" : remap de tous les identifiants text (aucun conflit d'id possible, aucun
    ecrasement) ; mode "merge" : ids conserves, lignes identiques ignorees, divergences
    = conflits. on_conflict "fail" leve ImportConflictError, "skip" ignore les divergences.
    Les investigations importees en "running" passent en "suspended" : aucune reprise de
    recherche automatique (D5.7.2)."""
    from ..ids import new_id

    report: dict[str, Any] = {"mode": mode, "inserted": {}, "skipped": {}, "remapped": 0, "conflicts": [], "normalized_states": []}
    deferred_updates: list[tuple[str, str, Any, str, Any]] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            if mode == "merge":
                conflicts = await detect_conflicts(conn, payload)
                if conflicts:
                    report["conflicts"] = conflicts
                    if on_conflict == "fail":
                        raise ImportConflictError(conflicts)
            id_map: dict[str, dict[str, str]] = {t: {} for t in IMPORT_ORDER}
            if mode == "add":
                for table in IMPORT_ORDER:
                    if table == "proof_files":
                        continue
                    for row in payload.get(table, []):
                        if not TABLES[table].get("serial"):
                            id_map[table][row[TABLES[table]["pk"]]] = new_id(table[:3])

            for table in IMPORT_ORDER:
                spec = TABLES[table]
                cols = spec["cols"]
                pk = spec["pk"]
                refs = spec["refs"]
                deferred = set(spec.get("deferred", []))
                target_ref = spec.get("target_ref", {})
                inserted = 0
                skipped = 0
                for row in payload.get(table, []):
                    new_row = dict(row)
                    if mode == "add" and not spec.get("serial") and table != "proof_files":
                        new_row[pk] = id_map[table][row[pk]]
                    if spec.get("serial"):
                        new_row.pop("id", None)
                    if mode == "merge" and not spec.get("serial"):
                        existing = await conn.fetchrow(f"SELECT 1 FROM {table} WHERE {pk} = $1", row[pk])
                        if existing is not None:
                            skipped += 1
                            continue
                    pending_deferred: list[tuple[str, Any]] = []
                    for col, ref_table in refs.items():
                        if new_row.get(col) is not None:
                            if col in deferred:
                                mapped = new_row[col]
                                if mode == "add" and not TABLES[ref_table].get("serial"):
                                    mapped = id_map[ref_table].get(new_row[col])
                                    if mapped is None:
                                        report.setdefault("dangling_refs", []).append({"table": table, "id": new_row.get(pk), "column": col, "missing": new_row[col], "ref_table": ref_table})
                                pending_deferred.append((col, mapped))
                                new_row[col] = None
                            elif mode == "add" and not TABLES[ref_table].get("serial"):
                                mapped = id_map[ref_table].get(new_row[col])
                                if mapped is None:
                                    report.setdefault("dangling_refs", []).append({"table": table, "id": new_row.get(pk), "column": col, "missing": new_row[col], "ref_table": ref_table})
                                new_row[col] = mapped
                    if table == "decisions" and new_row.get("target_id") is not None:
                        rt = target_ref.get(new_row.get("target_type"))
                        if rt and mode == "add":
                            mapped = id_map[rt].get(new_row["target_id"])
                            if mapped is None:
                                report.setdefault("dangling_refs", []).append({"table": table, "id": new_row.get(pk), "column": "target_id", "missing": new_row["target_id"], "ref_table": rt})
                            new_row["target_id"] = mapped
                    if table == "investigations" and new_row.get("state") == "running":
                        new_row["state"] = "suspended"
                        report["normalized_states"].append(new_row[pk])
                    if new_row.get("idempotency_key"):
                        clash = await conn.fetchrow(
                            f"SELECT 1 FROM {table} WHERE idempotency_key = $1 AND {pk} <> $2",
                            new_row["idempotency_key"], new_row.get(pk) or "",
                        )
                        if clash is not None:
                            new_row["idempotency_key"] = None
                            report.setdefault("regenerated_keys", []).append({"table": table, "id": new_row.get(pk)})
                    values = []
                    for c in cols:
                        if c == "id" and spec.get("serial"):
                            continue
                        v = new_row.get(c)
                        if c in JSONB_COLS.get(table, set()):
                            values.append(_json(v))
                        elif isinstance(v, str) and c in DATE_COLS.get(table, set()) and v:
                            values.append(date.fromisoformat(v))
                        elif isinstance(v, str) and c.endswith(("_at", "_before", "ed_at")) and v and not isinstance(v, (datetime, date)):
                            values.append(_parse_dt(v))
                        else:
                            values.append(v)
                    placeholders = ", ".join(f"${i+1}" + ("::jsonb" if c in JSONB_COLS.get(table, set()) else "") for i, c in enumerate([c for c in cols if not (c == "id" and spec.get("serial"))]))
                    insert_cols = [c for c in cols if not (c == "id" and spec.get("serial"))]
                    sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"
                    if table == "proof_files":
                        sql += " ON CONFLICT (sha256) DO NOTHING"
                    await conn.execute(sql, *values)
                    for col, mapped in pending_deferred:
                        deferred_updates.append((table, pk, new_row[pk], col, mapped))
                    if mode == "add" and not spec.get("serial") and table != "proof_files":
                        report["remapped"] += 1
                    inserted += 1
                report["inserted"][table] = inserted
                report["skipped"][table] = skipped
            for table, pk_col, pk_val, col, mapped in deferred_updates:
                await conn.execute(f"UPDATE {table} SET {col} = $1 WHERE {pk_col} = $2", mapped, pk_val)
    return report


class ImportConflictError(Exception):
    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__(f"{len(conflicts)} conflit(s) d'import detecte(s)")
        self.conflicts = conflicts
