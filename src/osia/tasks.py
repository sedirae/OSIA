from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import asyncpg

from .ai.schemas import Extraction, PlanProposal, Synthesis
from .connectors.base import FetchRequest, TrustLevel
from .models import ClaimNature, OpKind, PolicyDeny, StopReason, SupportLevel
from .policies.limits import limits_from_record

if TYPE_CHECKING:
    from .engine import Engine


@dataclass
class TaskContext:
    engine: "Engine"


TaskHandler = Callable[[asyncpg.Record, TaskContext], Awaitable[dict[str, Any]]]


async def handle_plan(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    limits = limits_from_record(inv)
    plan = await engine.broker.call(
        "planning",
        prompt="Décomposer l'objectif en sous-objectifs et requêtes source",
        input_data={"objective": inv["objective"], "hints": inv["hints"], "title": inv["title"]},
        response_model=PlanProposal,
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    queries = plan.source_queries[: limits.max_source_requests]
    for query in queries:
        await engine.repo.insert_task(
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            kind="source_query",
            payload={"query": query, "connector_id": "simulated.web"},
            depth=task["depth"],
            priority=10,
        )
    await engine.bus.emit(
        type="plan.revised",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={"sub_objectives": plan.sub_objectives, "queries": queries},
    )
    return {"sub_objectives": plan.sub_objectives, "queries": queries}


async def handle_source_query(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    payload = task["payload"]
    connector = engine.registry.get(payload["connector_id"])
    if connector is None:
        raise PolicyDeny("connecteur_non_autorise", "source")
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
        await engine.bus.emit(
            type="discovery",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={"query": payload["query"], "cached": True, "fetched_at": cached.get("fetched_at")},
        )
        return {"cached": True, "connector_id": connector.manifest.id, "query": payload["query"], "result": cached}
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
    await engine.policy.mark_in_flight(decision.op_id)
    try:
        async with engine.external_semaphore:
            result = await asyncio.wait_for(
                connector.fetch(FetchRequest(query=payload["query"])),
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
        raise RuntimeError(f"timeout_source:{decision.timeout_seconds}s") from exc
    except Exception as exc:
        await engine.policy.mark_uncertain(decision.op_id)
        await engine.bus.emit(
            type="op.uncertain",
            investigation_id=inv["id"],
            branch_id=task["branch_id"],
            payload={"op_id": decision.op_id, "error": str(exc)},
        )
        raise
    proof = await engine.filestore.store_proof(
        investigation_id=inv["id"],
        content=result.content.encode("utf-8"),
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
        },
        ttl_hours,
    )
    await engine.policy.complete_op(decision.op_id, {"http_status": result.provenance.http_status})
    await engine.bus.emit(
        type="discovery",
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        payload={"query": payload["query"], "url": result.provenance.url, "proof_sha256": proof["sha256"]},
    )
    extraction = await engine.broker.call(
        "extraction",
        prompt="Extraire entités et relations du contenu collecté",
        input_data={"content": result.extracted_text or result.content},
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
    return {"query": payload["query"], "proof_sha256": proof["sha256"], "entities": len(extraction.entities)}


async def handle_synthesize(task: asyncpg.Record, ctx: TaskContext) -> dict[str, Any]:
    engine = ctx.engine
    inv = await engine.repo.get_investigation(task["investigation_id"])
    if inv["state"] != "running":
        return {"skipped": f"investigation {inv['state']}"}
    limits = limits_from_record(inv)
    synthesis = await engine.broker.call(
        "synthesis",
        prompt="Synthétiser les acquis et évaluer l'étayage de l'objectif",
        input_data={"objective": inv["objective"], "depth": task["depth"]},
        response_model=Synthesis,
        investigation_id=inv["id"],
        branch_id=task["branch_id"],
        task_id=task["id"],
        depth=task["depth"],
    )
    proof_rows = await engine.repo.list_proof_refs(inv["id"])
    proof_ids = []
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
            await engine.repo.insert_task(
                investigation_id=inv["id"],
                branch_id=task["branch_id"],
                kind="source_query",
                payload={"query": followup, "connector_id": "simulated.web"},
                depth=task["depth"] + 1,
                priority=5,
            )
        return {"conclusion": synthesis.conclusion, "rebond": task["depth"] + 1}
    await engine.orchestrator.stop(inv["id"], StopReason.DEPTH_LIMIT)
    return {"conclusion": synthesis.conclusion, "stop": "depth_limit"}


DEFAULT_HANDLERS: dict[str, TaskHandler] = {
    "plan": handle_plan,
    "source_query": handle_source_query,
    "synthesize": handle_synthesize,
}
