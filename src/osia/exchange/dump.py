from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

import asyncpg

from .archive import ArchiveError

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
        # F10 : reservation_id est une vraie FK (remappée comme les autres en mode "add")
        "refs": {"investigation_id": "investigations", "task_id": "tasks", "reservation_id": "reservations"},
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

# Contrat des références EMBARQUÉES dans les colonnes JSONB (audit F10, T7.1/T7.6) : remappées
# comme les colonnes de refs en mode "add". "ref_list" = tableau d'identifiants d'une même table ;
# "deep" = arbre quelconque dont toute chaîne résolvant sans ambiguïté vers un identifiant importé
# est remappée (sinon elle est laissée telle quelle et signalée dans report["ambiguous_refs"]).
JSON_REF_CONTRACT: dict[str, dict[str, dict[str, str]]] = {
    "relations": {"proof_ids": {"kind": "ref_list", "ref_table": "proof_refs"}},
    "assertions": {
        "proof_ids": {"kind": "ref_list", "ref_table": "proof_refs"},
        "contradicted_by": {"kind": "ref_list", "ref_table": "assertions"},
    },
    "decisions": {"payload": {"kind": "deep"}},
    "tasks": {"payload": {"kind": "deep"}},
    "external_ops": {"result": {"kind": "deep"}},
    "events": {"payload": {"kind": "deep"}},
}

# Forme des identifiants OSIA (new_id : prefixe 3 lettres + 16 caractères hex).
_ID_LIKE = re.compile(r"^[a-z]{3}_[0-9a-f]{16}$")


def _remap_ref_list(values: Any, ref_table: str, id_map: dict[str, dict[str, str]], *, table: str, row_id: Any, col: str, report: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    for v in values or []:
        if not isinstance(v, str):
            out.append(v)
            continue
        mapped = id_map.get(ref_table, {}).get(v)
        if mapped is None:
            report.setdefault("dangling_refs", []).append({"table": table, "id": row_id, "column": col, "missing": v, "ref_table": ref_table})
            out.append(v)
        else:
            out.append(mapped)
    return out


def _remap_json_deep(value: Any, id_map: dict[str, dict[str, str]], *, table: str, row_id: Any, col: str, report: dict[str, Any]) -> Any:
    """Remappe récursivement toute chaîne qui est un identifiant importé (mode add, F10)."""

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            hits = [t for t in IMPORT_ORDER if not TABLES[t].get("serial") and t != "proof_files" and v in id_map.get(t, {})]
            if len(hits) == 1:
                return id_map[hits[0]][v]
            if len(hits) > 1:
                report.setdefault("ambiguous_refs", []).append({"table": table, "id": row_id, "column": col, "value": v, "tables": sorted(hits)})
            return v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(value)


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for x in value:
            yield from _iter_strings(x)
    elif isinstance(value, dict):
        for x in value.values():
            yield from _iter_strings(x)


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

    branch_ids restreint l'export a la FERMETURE du périmètre choisi (audit F12, T7.4/T7.8) :
    branches/tasks/assertions/relations/events/reservations/external_ops/ledger des branches
    choisies, décisions portant sur ces assertions/relations, et preuves (proof_refs +
    proof_files) référencées par ces assertions/relations. Les entites, identifiants et
    match_proposals restent ceux de l'investigation (pas de branche propre). Les branches
    ANCESTRALES d'une branche choisie ne sont pas remontées (parent_branch_id peut alors être
    signalé dangling a l'import). exclusions retire des tables techniques/financieres."""
    exclusions = exclusions or set()
    payload: dict[str, list[dict[str, Any]]] = {}
    async with pool.acquire() as conn:
        # Périmètre branch_ids : identifiants des lignes retenues, utilisés pour la fermeture
        # des décisions, des preuves, des opérations externes et du ledger.
        sel_assertions: list[str] = []
        sel_relations: list[str] = []
        sel_tasks: list[str] = []
        sel_reservations: list[str] = []
        if branch_ids:
            sel_assertions = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM assertions WHERE investigation_id = $1 AND (branch_id IS NULL OR branch_id = ANY($2))",
                    investigation_id, branch_ids,
                )
            ]
            sel_relations = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM relations WHERE investigation_id = $1 AND (branch_id IS NULL OR branch_id = ANY($2))",
                    investigation_id, branch_ids,
                )
            ]
            sel_tasks = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM tasks WHERE investigation_id = $1 AND (branch_id IS NULL OR branch_id = ANY($2))",
                    investigation_id, branch_ids,
                )
            ]
            sel_reservations = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM reservations WHERE investigation_id = $1 AND (branch_id IS NULL OR branch_id = ANY($2))",
                    investigation_id, branch_ids,
                )
            ]
        proof_scope_sql = (
            "SELECT DISTINCT p2.id FROM proof_refs p2 WHERE p2.investigation_id = $1 AND p2.id IN ("
            "SELECT jsonb_array_elements_text(a.proof_ids) FROM assertions a "
            "WHERE a.investigation_id = $1 AND (a.branch_id IS NULL OR a.branch_id = ANY($2)) "
            "UNION "
            "SELECT jsonb_array_elements_text(r.proof_ids) FROM relations r "
            "WHERE r.investigation_id = $1 AND (r.branch_id IS NULL OR r.branch_id = ANY($2))"
            ")"
        )
        for table in IMPORT_ORDER:
            if table in exclusions:
                payload[table] = []
                continue
            if table == "investigations":
                rows = await conn.fetch("SELECT * FROM investigations WHERE id = $1", investigation_id)
            elif table == "proof_files":
                if branch_ids:
                    rows = await conn.fetch(
                        "SELECT DISTINCT pf.* FROM proof_files pf JOIN proof_refs pr ON pr.proof_sha256 = pf.sha256 "
                        f"WHERE pr.id IN ({proof_scope_sql}) ORDER BY pf.sha256",
                        investigation_id, branch_ids,
                    )
                else:
                    rows = await conn.fetch(
                        "SELECT DISTINCT pf.* FROM proof_files pf JOIN proof_refs pr ON pr.proof_sha256 = pf.sha256 "
                        "WHERE pr.investigation_id = $1 ORDER BY pf.sha256",
                        investigation_id,
                    )
            elif table == "proof_refs" and branch_ids:
                rows = await conn.fetch(
                    f"SELECT * FROM proof_refs WHERE id IN ({proof_scope_sql}) ORDER BY fetched_at",
                    investigation_id, branch_ids,
                )
            elif branch_ids and table == "decisions":
                # Fermeture (F12) : décisions dont la cible est dans le périmètre (assertion ou
                # relation retenue) ; les cibles entity/match_proposal restent globales.
                rows = await conn.fetch(
                    "SELECT * FROM decisions WHERE investigation_id = $1 "
                    "AND (assertion_id IS NULL OR assertion_id = ANY($2)) "
                    "AND (target_type IS NULL OR target_type IN ('entity', 'match_proposal') "
                    "     OR (target_type = 'assertion' AND target_id = ANY($2)) "
                    "     OR (target_type = 'relation' AND target_id = ANY($3))) "
                    "ORDER BY created_at",
                    investigation_id, sel_assertions or ["__none__"], sel_relations or ["__none__"],
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
            elif branch_ids and table == "external_ops":
                # F12 (audit PR #22 P2-1) : les opérations externes suivent leurs tâches du
                # périmètre — sinon fuite des métadonnées d'activité des autres branches.
                rows = await conn.fetch(
                    "SELECT * FROM external_ops WHERE investigation_id = $1 AND (task_id IS NULL OR task_id = ANY($2)) "
                    "ORDER BY created_at",
                    investigation_id, sel_tasks or ["__none__"],
                )
            elif branch_ids and table == "ledger":
                # F12 (audit PR #22 P2-1) : le ledger suit les réservations du périmètre.
                rows = await conn.fetch(
                    "SELECT * FROM ledger WHERE investigation_id = $1 AND (reservation_id IS NULL OR reservation_id = ANY($2)) "
                    "ORDER BY created_at",
                    investigation_id, sel_reservations or ["__none__"],
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


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse une valeur horodatement serialisee en ISO 8601, sinon None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _same_value(left: Any, right: Any) -> bool:
    """Comparaison de deux valeurs : les horodatages ISO 8601 sont compares comme instants
    (to_jsonb rend la session dans le fuseau local, l'archive stocke en UTC)."""
    dl, dr = _parse_dt(left), _parse_dt(right)
    if dl is not None and dr is not None:
        return dl == dr
    return json.dumps(_norm_val(left), sort_keys=True, default=str) == json.dumps(_norm_val(right), sort_keys=True, default=str)


async def detect_conflicts(
    conn: asyncpg.Connection,
    payload: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Detecte les collisions d'identifiants et les contenus divergents (T7.6, D5.7.2)."""
    validate_payload(payload)
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
            same = all(_same_value(left.get(k), row.get(k)) for k in spec["cols"])
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

    validate_payload(payload)

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
                    # F10 : remap des références embarquées dans les colonnes JSONB (mode add)
                    if mode == "add":
                        for col, contract in JSON_REF_CONTRACT.get(table, {}).items():
                            v = new_row.get(col)
                            if v is None:
                                continue
                            if contract["kind"] == "ref_list":
                                new_row[col] = _remap_ref_list(v, contract["ref_table"], id_map, table=table, row_id=row.get(pk), col=col, report=report)
                            else:
                                new_row[col] = _remap_json_deep(v, id_map, table=table, row_id=row.get(pk), col=col, report=report)
                    if table == "investigations" and new_row.get("state") == "running":
                        new_row["state"] = "suspended"
                        report["normalized_states"].append(new_row[pk])
                    if table == "reservations" and new_row.get("state") == "reserved":
                        # Règle explicite (audit F10) : une réservation importée non résolue ne
                        # doit pas peser sur les plafonds financiers locaux (elle ne sera jamais
                        # consommée ici) ; l'état d'origine reste dans l'archive exportée.
                        new_row["state"] = "released"
                        report.setdefault("released_reservations", []).append(new_row.get(pk))
                    if new_row.get("idempotency_key"):
                        clash = await conn.fetchrow(
                            f"SELECT 1 FROM {table} WHERE idempotency_key = $1 AND {pk} <> $2",
                            new_row["idempotency_key"], new_row.get(pk) or "",
                        )
                        if clash is not None:
                            # F10 : reservations.idempotency_key est NOT NULL -> on régénère une
                            # clé fraîche plutôt que NULL (sinon l'insert échoue en mode add).
                            new_row["idempotency_key"] = new_id("key") if table == "reservations" else None
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
            # F10 / T7.6 : vérification d'intégrité référentielle métier APRÈS import — toute
            # référence (colonne FK, target_ref ou embarquée dans le JSON) doit résoudre en base.
            dangling = await _verify_refs(conn, payload, mode=mode, id_map=id_map)
            if dangling:
                report.setdefault("dangling_refs", []).extend(dangling)
            report["integrity"] = "dangling" if report.get("dangling_refs") else "ok"
    return report


def validate_payload(payload: dict) -> None:
    """Vérifier la forme des lignes avant accès base, remappage et staging."""
    for table, rows in payload.items():
        if table not in TABLES or not isinstance(rows, list):
            raise ArchiveError("table d’archive inconnue ou invalide")
        spec = TABLES[table]
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ArchiveError(f"ligne invalide dans {table}")
            key = row.get(spec["pk"])
            valid = type(key) is int if spec.get("serial") else isinstance(key, str) and bool(key)
            if not valid or key in seen:
                raise ArchiveError(f"identifiant absent, invalide ou dupliqué dans {table}")
            seen.add(key)


_ID_TABLES = [t for t in IMPORT_ORDER if not TABLES[t].get("serial") and t != "proof_files"]


async def _id_exists_anywhere(conn: asyncpg.Connection, value: str) -> bool:
    for t in _ID_TABLES:
        if await conn.fetchval(f"SELECT 1 FROM {t} WHERE {TABLES[t]['pk']} = $1", value):
            return True
    return False


async def _verify_refs(
    conn: asyncpg.Connection,
    payload: dict[str, list[dict[str, Any]]],
    *,
    mode: str,
    id_map: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Vérifie après import que chaque référence du payload résout vers une ligne insérée
    (ou préexistante en mode merge). Retourne les références rompues."""
    dangling: list[dict[str, Any]] = []

    def resolve(ref_table: str, value: Any) -> Any:
        if value is None:
            return None
        if mode == "add" and not TABLES[ref_table].get("serial") and ref_table != "proof_files":
            return id_map.get(ref_table, {}).get(value)
        return value

    async def check(ref_table: str, target: Any, *, table: str, rid: Any, col: str, missing: Any) -> None:
        if target is None:
            return
        ok = await conn.fetchval(f"SELECT 1 FROM {ref_table} WHERE {TABLES[ref_table]['pk']} = $1", target)
        if not ok:
            dangling.append({"table": table, "id": rid, "column": col, "missing": missing, "ref_table": ref_table})

    for table in IMPORT_ORDER:
        spec = TABLES[table]
        pk = spec["pk"]
        target_ref = spec.get("target_ref", {})
        for row in payload.get(table, []):
            rid = row.get(pk)
            for col, ref_table in spec["refs"].items():
                await check(ref_table, resolve(ref_table, row.get(col)), table=table, rid=rid, col=col, missing=row.get(col))
            if table == "proof_refs" and row.get("proof_sha256"):
                # F10 (audit PR #22 P3-5) : proof_sha256 doit résoudre vers un proof_files
                # (non remappé : la clé est le contenu, stable entre instances).
                ok = await conn.fetchval("SELECT 1 FROM proof_files WHERE sha256 = $1", row["proof_sha256"])
                if not ok:
                    dangling.append({"table": table, "id": rid, "column": "proof_sha256", "missing": row["proof_sha256"], "ref_table": "proof_files"})
            if row.get("target_id") is not None:
                rt = target_ref.get(row.get("target_type"))
                if rt:
                    await check(rt, resolve(rt, row["target_id"]), table=table, rid=rid, col="target_id", missing=row["target_id"])
            for col, contract in JSON_REF_CONTRACT.get(table, {}).items():
                v = row.get(col)
                if v is None:
                    continue
                if contract["kind"] == "ref_list":
                    for item in v or []:
                        await check(contract["ref_table"], resolve(contract["ref_table"], item), table=table, rid=rid, col=col, missing=item)
                else:
                    for s in _iter_strings(v):
                        if not _ID_LIKE.match(s):
                            continue
                        hits = [t for t in _ID_TABLES if s in id_map.get(t, {})] if mode == "add" else []
                        if len(hits) == 1:
                            await check(hits[0], id_map[hits[0]][s], table=table, rid=rid, col=col, missing=s)
                        elif not hits and not await _id_exists_anywhere(conn, s):
                            dangling.append({"table": table, "id": rid, "column": col, "missing": s, "ref_table": "?"})
    return dangling


class ImportConflictError(Exception):
    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__(f"{len(conflicts)} conflit(s) d'import detecte(s)")
        self.conflicts = conflicts
