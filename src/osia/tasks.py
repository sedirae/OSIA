from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import asyncpg

from .ai.schemas import Extraction, PlanProposal, Synthesis
from .connectors.base import FetchRequest, FetchResult, Provenance, TrustLevel
from .connectors.http import HttpStatusError
from .connectors.select import select_connector_id
from .models import ClaimNature, OpKind, PolicyDeny, StopReason, SupportLevel
from .policies.limits import limits_from_record

if TYPE_CHECKING:
    from .engine import Engine


@dataclass
class TaskContext:
    engine: "Engine"


TaskHandler = Callable[[asyncpg.Record, TaskContext], Awaitable[dict[str, Any]]]

# Bornes du contexte de synthèse (F06) : le prompt reste borné quelle que soit la taille du graphe.
SYNTHESIS_MAX_PROOFS = 50
SYNTHESIS_MAX_ASSERTIONS = 100
SYNTHESIS_MAX_RELATIONS = 200
SYNTHESIS_MAX_DECISIONS = 100
SYNTHESIS_MAX_TEXT = 2000


def _trunc(value: Any, limit: int = SYNTHESIS_MAX_TEXT) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _plan_source_payloads(engine: "Engine", plan: PlanProposal, limits: Any, inv_id: str, branch_id: str | None) -> list[dict[str, Any]]:
    """F05 : propositions typées validées contre le registre ; à défaut, sélection par capacités.

    Une proposition IA invalide ne fait pas échouer le plan : elle est journalisée (événement
    `plan.selection_rejected`) et remplacée par la sélection déterministe par capacités."""
    payloads: list[dict[str, Any]] = []
    selections = plan.selections[: limits.max_source_requests]
    if selections:
        for sel in selections:
            try:
                connector_id, simulated = select_connector_id(engine.registry, sel.query, requested_id=sel.connector_id)
            except PolicyDeny:
                await engine.bus.emit(
                    type="plan.selection_rejected",
                    investigation_id=inv_id,
                    branch_id=branch_id,
                    payload={"connector_id": sel.connector_id, "query": sel.query, "reason": "connecteur non actif dans le registre"},
                )
                connector_id, simulated = select_connector_id(engine.registry, sel.query)
            payloads.append({"query": sel.query, "connector_id": connector_id, "params": dict(sel.params), "simulated": simulated})
    else:
        for query in plan.source_queries[: limits.max_source_requests]:
            connector_id, simulated = select_connector_id(engine.registry, query)
            payloads.append({"query": query, "connector_id": connector_id, "simulated": simulated})
    return payloads


async def handle_plan(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    limits = limits_from_record(inv)
    # F08 : le plan décompose l'objectif de la BRANCHE (pas celui de l'investigation parente)
    branch = await engine.repo.get_branch(task["branch_id"]) if task["branch_id"] else None
    objective = (branch["objective"] if branch and branch["objective"] else None) or inv["objective"]
    plan = await engine.broker.call(
        "planning",
        prompt=(
            "Décomposer l'objectif en sous-objectifs et requêtes source typées : pour chaque requête, "
            "choisir un connector_id parmi available_connectors selon ses capabilities et son scope"
        ),
        input_data={
            "objective": objective,
            "hints": inv["hints"],
            "title": inv["title"],
            "branch_id": task["branch_id"],
            "available_connectors": engine.registry.list(),
        },
        response_model=PlanProposal,
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    payloads = await _plan_source_payloads(engine, plan, limits, inv["id"], task["branch_id"])
    for payload in payloads:
        await engine.repo.insert_task(
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            kind="source_query",
            payload=payload,
            depth=task["depth"],
            priority=10,
        )
    queries = [p["query"] for p in payloads]
    await engine.bus.emit(
        type="plan.revised",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={
            "sub_objectives": plan.sub_objectives,
            "queries": queries,
            "connectors": {p["query"]: p["connector_id"] for p in payloads},
            "simulated_sources": sorted({p["connector_id"] for p in payloads if p.get("simulated")}),
        },
    )
    return {"sub_objectives": plan.sub_objectives, "queries": queries, "source_tasks": payloads}


async def _extract_and_enqueue_synthesis(
    engine: "Engine",
    inv: asyncpg.Record,
    task: asyncpg.Record,
    payload: dict[str, Any],
    result: FetchResult,
    proof: dict[str, Any],
) -> Extraction:
    """Traitement métier commun à une collecte et à un hit cache (F09) : extraction IA,
    graphe (entités/relations) puis tâche de synthèse. Le cache évite l'I/O externe, pas le résultat."""
    extraction = await engine.broker.call(
        "extraction",
        prompt="Extraire entités et relations du contenu collecté",
        input_data={
            "content": result.extracted_text or result.content,
            "source_url": result.provenance.url,
            "proof_id": proof["proof_ref_id"],
        },
        response_model=Extraction,
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    entity_ids: dict[str, str] = {}
    for entity in extraction.entities:
        upserted = await engine.graph.upsert_entity(
            inv["id"],
            kind=entity.kind,
            data={"name": entity.name, "identifiers": entity.identifiers},
            identifiers=entity.identifiers,
            branch_id=task["branch_id"],
        )
        entity_ids[entity.name] = upserted["entity_id"]
    support_map = {
        "confirmed": SupportLevel.CORROBORE,
        "hypothesis": SupportLevel.A_CONFIRMER,
        "contradicted": SupportLevel.CONTRADICTOIRE,
    }
    for relation in extraction.relations:
        if relation.src in entity_ids and relation.dst in entity_ids:
            await engine.graph.add_relation(
                inv["id"],
                branch_id=task["branch_id"],
                src_id=entity_ids[relation.src],
                dst_id=entity_ids[relation.dst],
                type=relation.type,
                support_level=support_map.get(relation.status, SupportLevel.A_CONFIRMER),
                proof_ids=[proof["proof_ref_id"]],
                derivation="ia",
            )
    await engine.repo.insert_task(
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        kind="synthesize",
        payload={"query": payload["query"]},
        depth=task["depth"],
        priority=5,
    )
    return extraction


async def handle_source_query(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    payload = task["payload"]
    connector = engine.registry.get(payload["connector_id"])
    if connector is None:
        # F05 : connecteur explicitement demandé mais indisponible -> erreur de configuration
        # explicite, AUCUN repli silencieux sur un autre connecteur (ni sur la simulation).
        known = False
        list_fn = getattr(engine.registry, "list", None)
        if callable(list_fn):
            known = any(e["id"] == payload["connector_id"] for e in list_fn())
        raise PolicyDeny(
            f"connecteur_demande_indisponible:{payload['connector_id']}" if known else f"connecteur_inconnu:{payload['connector_id']}",
            "source",
        )
    # T5.1 : un connecteur EXPERIMENTAL exige une autorisation explicite persistée
    if connector.manifest.trust_level == TrustLevel.EXPERIMENTAL:
        allowed = await engine.repo.get_setting(f"allow_experimental:{connector.manifest.id}", False)
        if not allowed:
            raise PolicyDeny("experimental_sans_autorisation_explicite", "source")
    # CON-13 / B-ACC-06 : requête équivalente déjà satisfaite -> réutilisation du cache valide
    # (V1.4 : TTL 24 h par défaut, D4 §6.2 fraîcheur tracée) plutôt qu'un nouvel appel externe.
    ttl_hours = await engine.repo.get_setting("source_cache_ttl_hours", 24)
    cached = await engine.repo.cache_get(connector.manifest.id, payload["query"])
    if cached is not None:
        # F09 : un hit cache suit le MÊME traitement métier qu'une collecte (preuve rattachée,
        # extraction, synthèse) — il évite seulement l'appel externe redondant. La date et la
        # provenance d'origine sont conservées (entrée de cache non réécrite, événement tracé).
        raw_b64 = cached.get("raw_b64")
        result = FetchResult(
            content=cached.get("content", ""),
            provenance=Provenance(
                source_id=connector.manifest.id,
                url=cached.get("url"),
                fetched_at=_parse_dt(cached.get("fetched_at")),
                http_status=cached.get("http_status"),
            ),
            media_type=cached.get("media_type", "application/json"),
            extracted_text=cached.get("extracted_text"),
            raw_bytes=base64.b64decode(raw_b64) if raw_b64 else None,  # F13 : original conservé via le cache
        )
        proof = await engine.filestore.store_proof(
            investigation_id=inv["id"],
            content=result.raw_bytes if result.raw_bytes is not None else result.content.encode("utf-8"),
            source_url=result.provenance.url,
            media_type=result.media_type,
            label=payload["query"],
            connector_id=result.provenance.source_id,
        )
        await engine.bus.emit(
            type="discovery",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={
                "query": payload["query"],
                "cached": True,
                "fetched_at": cached.get("fetched_at"),
                "url": result.provenance.url,
                "proof_sha256": proof["sha256"],
            },
        )
        engine.techlog.log(
            "tasks", "source.query",
            investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"],
            detail={"connector_id": connector.manifest.id, "cached": True, "http_status": result.provenance.http_status},
        )
        await _extract_and_enqueue_synthesis(engine, inv, task, payload, result, proof)
        return {"cached": True, "connector_id": connector.manifest.id, "query": payload["query"], "proof_sha256": proof["sha256"], "result": cached}
    decision = await engine.policy.authorize(
        investigation_id=inv["id"],
        kind=OpKind.SOURCE_REQUEST,
        target=connector.manifest.id,
        is_paid=connector.manifest.paid,
        cost_estimated_cents=connector.manifest.cost_per_call_cents,
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    if not decision.allowed:
        raise PolicyDeny(decision.reason or "refus_politique", "source")
    started = time.monotonic()
    try:
        async with engine.external_semaphore:
            # F04 : revalidation atomique immédiatement avant l'I/O (attente du sémaphore incluse)
            recheck = await engine.policy.revalidate(decision.op_id, investigation_id=inv["id"])
            if not recheck.allowed:
                await engine.policy.cancel_op(decision.op_id, reason=recheck.reason or "revalidation_refusee")
                raise PolicyDeny(recheck.reason or "revalidation_refusee", "source")
            if not await engine.policy.mark_in_flight(decision.op_id):
                # P2-1 : annulée entre la revalidation et l'envoi (stop) — jamais envoyée
                await engine.policy.cancel_op(decision.op_id, reason="operation_annulee_avant_envoi")
                raise PolicyDeny("operation_annulee_avant_envoi", "source")
            result = await asyncio.wait_for(
                connector.fetch(FetchRequest(query=payload["query"], params=payload.get("params") or {})),
                timeout=decision.timeout_seconds or 15,
            )
    except asyncio.TimeoutError as exc:
        await engine.policy.mark_uncertain(decision.op_id)
        await engine.bus.emit(
            type="op.uncertain",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={"op_id": decision.op_id, "error": f"timeout_source:{decision.timeout_seconds}s"},
        )
        engine.techlog.log("tasks", "source.query", level="error", investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"], op_id=decision.op_id, duration_ms=int((time.monotonic() - started) * 1000), error=f"timeout_source:{decision.timeout_seconds}s", detail={"connector_id": connector.manifest.id})
        raise RuntimeError(f"timeout_source:{decision.timeout_seconds}s") from exc
    except HttpStatusError as exc:
        # F13 : 404/429/500… = erreur HTTP distincte d'un résultat vide ; jamais stockée comme preuve.
        await engine.policy.mark_uncertain(decision.op_id)
        await engine.bus.emit(
            type="op.uncertain",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={"op_id": decision.op_id, "error": f"http_status:{exc.status}", "http_status": exc.status, "url": exc.url},
        )
        engine.techlog.log("tasks", "source.query", level="error", investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"], op_id=decision.op_id, duration_ms=int((time.monotonic() - started) * 1000), error=f"http_status:{exc.status}", detail={"connector_id": connector.manifest.id, "http_status": exc.status})
        raise RuntimeError(f"http_status:{exc.status}") from exc
    except Exception as exc:
        await engine.policy.mark_uncertain(decision.op_id)
        await engine.bus.emit(
            type="op.uncertain",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={"op_id": decision.op_id, "error": str(exc)},
        )
        engine.techlog.log("tasks", "source.query", level="error", investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"], op_id=decision.op_id, duration_ms=int((time.monotonic() - started) * 1000), error=str(exc), detail={"connector_id": connector.manifest.id})
        raise
    # F13 / B7 §9.1 : validation sémantique du connecteur AVANT stockage, cache et exploitation.
    # Une réponse 200 de structure invalide est refusée (pas transformée en « absence de résultat »).
    try:
        parsed = json.loads(result.content)
    except (ValueError, TypeError):
        parsed = result.content
    problems = connector.validate_response(parsed)
    if problems:
        # l'appel externe a bien eu lieu (coût encouru) : l'opération est soldée, la preuve refusée
        await engine.policy.complete_op(decision.op_id, {"http_status": result.provenance.http_status, "invalid_response": problems})
        engine.techlog.log("tasks", "source.query", level="error", investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"], op_id=decision.op_id, duration_ms=int((time.monotonic() - started) * 1000), error="reponse_invalide", detail={"connector_id": connector.manifest.id, "problems": problems})
        raise RuntimeError("reponse_invalide:" + "; ".join(problems))
    proof = await engine.filestore.store_proof(
        investigation_id=inv["id"],
        # F13 / T2.2 : la preuve conserve les OCTETS ORIGINAUX (raw_bytes), pas le texte normalisé
        content=result.raw_bytes if result.raw_bytes is not None else result.content.encode("utf-8"),
        source_url=result.provenance.url,
        media_type=result.media_type,
        label=payload["query"],
        connector_id=result.provenance.source_id,
    )
    await engine.repo.cache_set(
        connector.manifest.id,
        payload["query"],
        {
            "content": result.content,
            "media_type": result.media_type,
            "extracted_text": result.extracted_text,
            "url": result.provenance.url,
            "http_status": result.provenance.http_status,
            "raw_b64": base64.b64encode(result.raw_bytes).decode("ascii") if result.raw_bytes is not None else None,
        },
        ttl_hours,
    )
    await engine.policy.complete_op(decision.op_id, {"http_status": result.provenance.http_status})
    engine.techlog.log("tasks", "source.query", investigation_id=inv["id"], branch_id=task["branch_id"], task_id=task["id"], op_id=decision.op_id, duration_ms=int((time.monotonic() - started) * 1000), detail={"connector_id": connector.manifest.id, "http_status": result.provenance.http_status})
    await engine.bus.emit(
        type="discovery",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={"query": payload["query"], "url": result.provenance.url, "proof_sha256": proof["sha256"]},
    )
    extraction = await _extract_and_enqueue_synthesis(engine, inv, task, payload, result, proof)
    return {"query": payload["query"], "proof_sha256": proof["sha256"], "entities": len(extraction.entities)}


async def _build_synthesis_input(engine: "Engine", inv: asyncpg.Record, task: asyncpg.Record) -> tuple[dict[str, Any], list]:
    """F06 : entrée de synthèse = objectif + branche + preuves (id stables) + assertions +
    relations + décisions humaines + contradictions, le tout borné en taille."""
    proof_rows = await engine.repo.list_proof_refs(inv["id"])
    proofs_ctx = [
        {
            "id": r["id"],
            "sha256": r["proof_sha256"],
            "source_url": r["source_url"],
            "label": _trunc(r["label"], 500),
            "connector_id": r["connector_id"],
            "media_type": r["media_type"],
            "size_bytes": r["size_bytes"],
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        }
        for r in proof_rows[:SYNTHESIS_MAX_PROOFS]
    ]
    assertions = await engine.graph.list_assertions(inv["id"], branch_id=task["branch_id"])

    def _ids(value: Any) -> list[str]:
        return list(value) if isinstance(value, (list, tuple)) else []

    assertions_ctx = [
        {
            "id": a["id"],
            "statement": _trunc(a["statement"]),
            "nature": a["nature"],
            "support_level": a["support_level"],
            "human_decision": a["human_decision"],
            "decisive": a["decisive"],
            "proof_ids": _ids(a["proof_ids"]),
            "contradicted_by": _ids(a["contradicted_by"]),
        }
        for a in assertions[:SYNTHESIS_MAX_ASSERTIONS]
    ]
    relations_ctx = [
        {
            "src_id": r["src_id"],
            "dst_id": r["dst_id"],
            "type": r["type"],
            "support_level": r["support_level"],
            "proof_ids": _ids(r["proof_ids"]),
        }
        for r in (await engine.graph.list_relations(inv["id"], branch_id=task["branch_id"], limit=SYNTHESIS_MAX_RELATIONS))[:SYNTHESIS_MAX_RELATIONS]
    ]
    decisions_ctx = [
        {
            "id": d["id"],
            "assertion_id": d["assertion_id"],
            "action": d["action"],
            # P2-1 (audit PR #20) : payload jsonb = dict, sérialisé PUIS tronqué — le contexte
            # de synthèse reste borné quelle que soit la taille du payload de la décision.
            "payload": _trunc(d["payload"] if isinstance(d["payload"], str) else json.dumps(d["payload"], ensure_ascii=False, default=str), 1000),
            "created_at": d["created_at"].isoformat() if d["created_at"] else None,
        }
        for d in (await engine.graph.list_decisions(inv["id"], limit=SYNTHESIS_MAX_DECISIONS))[:SYNTHESIS_MAX_DECISIONS]
    ]
    contradictions_ctx = [a for a in assertions_ctx if a["support_level"] == "contradictoire" or a["contradicted_by"]]
    input_data = {
        "objective": inv["objective"],
        "depth": task["depth"],
        "branch_id": task["branch_id"],
        "proofs": proofs_ctx,
        "assertions": assertions_ctx,
        "relations": relations_ctx,
        "decisions": decisions_ctx,
        "contradictions": contradictions_ctx,
        "output_contract": (
            "decisive_proof_ids doit contenir des id de preuves présents dans proofs (identifiants stables) ; "
            "decisive_sources des URLs présentes dans proofs[].source_url. Toute référence inventée est rejetée."
        ),
    }
    return input_data, proof_rows


async def handle_synthesize(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    if inv["state"] != "running":
        return {"skipped": f"investigation {inv['state']}"}
    limits = limits_from_record(inv)
    # F06 : la synthèse reçoit le contexte de preuves borné + graphe + décisions (pas seulement
    # {objective, depth}) ; le schéma JSON de sortie est transmis par le courtier (T8.6).
    input_data, proof_rows = await _build_synthesis_input(engine, inv, task)
    synthesis = await engine.broker.call(
        "synthesis",
        prompt="Synthétiser les acquis et évaluer l'étayage de l'objectif",
        input_data=input_data,
        response_model=Synthesis,
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    # F06 : identifiants de preuves stables d'abord, égalité d'URL en repli.
    valid_ids = {r["id"] for r in proof_rows}
    proof_ids = [pid for pid in synthesis.decisive_proof_ids if pid in valid_ids]
    for source in synthesis.decisive_sources:
        matched = [r["id"] for r in proof_rows if r["source_url"] and r["source_url"] == source]
        proof_ids.extend(matched)
    proof_ids = list(dict.fromkeys(proof_ids))
    support_map = {
        "documenté": SupportLevel.DOCUMENTE,
        "corroboré": SupportLevel.CORROBORE,
        "à confirmer": SupportLevel.A_CONFIRMER,
        "contradictoire": SupportLevel.CONTRADICTOIRE,
        "non établi": SupportLevel.NON_ETABLI,
    }
    assertion = await engine.graph.add_assertion(
        inv["id"],
        branch_id=task["branch_id"],
        statement=synthesis.conclusion,
        nature=ClaimNature.CONCLUSION_ANALYTIQUE,
        support_level=support_map.get(synthesis.support, SupportLevel.A_CONFIRMER),
        proof_ids=proof_ids,
        decisive=True,
        derivation="ia",
    )
    for contradiction in synthesis.contradictions:
        await engine.graph.add_assertion(
            inv["id"],
            branch_id=task["branch_id"],
            statement=contradiction,
            nature=ClaimNature.HYPOTHESE,
            support_level=SupportLevel.CONTRADICTOIRE,
            proof_ids=proof_ids,
            decisive=False,
            derivation="ia",
            contradicted_by=[assertion["id"]],
        )
    objectif = await engine.graph.objective_etaye(inv["id"], task["branch_id"])
    await engine.bus.emit(
        type="objective.evalue",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={**objectif, "proposition_ia": synthesis.objective_sufficiently_supported},
    )
    if objectif["etaye"]:
        await engine.orchestrator.stop(inv["id"], StopReason.OBJECTIVE)
        return {"conclusion": synthesis.conclusion, "stop": "objective_suffisamment_etaye", "objectif": objectif}
    if task["depth"] < limits.max_rebonds:
        for followup in synthesis.suggested_followups[: limits.max_source_requests]:
            # F05 : rebond routé comme une requête initiale (sélection par capacités), jamais
            # `simulated.web` en dur.
            connector_id, simulated = select_connector_id(engine.registry, followup)
            await engine.repo.insert_task(
                investigation_id=inv["id"],
                branch_id=task["branch_id"],
                kind="source_query",
                payload={"query": followup, "connector_id": connector_id, "simulated": simulated},
                depth=task["depth"] + 1,
                priority=5,
            )
        return {"conclusion": synthesis.conclusion, "rebond": task["depth"] + 1}
    # F08 : les pistes proposées mais non lancées (limite de profondeur) sont restituées
    # explicitement — TOUTES, pas seulement celles sous le plafond (P3-4 audit PR #21).
    followups_non_lancees = list(synthesis.suggested_followups)
    await engine.bus.emit(
        type="synthesis.followups_non_lances",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={"followups": followups_non_lancees, "reason": "depth_limit"},
    )
    await engine.orchestrator.stop(inv["id"], StopReason.DEPTH_LIMIT)
    return {"conclusion": synthesis.conclusion, "stop": "depth_limit", "followups_non_lancees": followups_non_lancees}


DEFAULT_HANDLERS: dict[str, TaskHandler] = {
    "plan": handle_plan,
    "source_query": handle_source_query,
    "synthesize": handle_synthesize,
}
