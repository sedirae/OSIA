"""CON-19 / T8.10 : évaluation REPRODUCTIBLE des modèles IA **par tâche**, indépendante des
fournisseurs.

- Jeux de cas embarqués (`EVAL_CASES`) : entrée + vérité terrain + réponse scriptée, rejouables
  hors ligne avec l'adaptateur simulé (aucune dépense API, T3.14).
- Métriques par cas et agrégées par rôle : conformité au schéma (T8.6), erreurs, latence (ms),
  coût (centimes), qualité d'extraction (précision/rappel/F1 sur les entités, T8.10).
- Le rapport produit est un relevé de résultats réels (mesures effectuées pendant l'exécution),
  sérialisable en JSON et comparable entre adaptateurs (fournisseurs, versions, modèles, prompts).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

from .base import AIAdapter
from .schemas import Extraction, PlanProposal, Synthesis
from .simulated import SimulatedAIAdapter


@dataclass
class EvalCase:
    """Un cas d'évaluation : rôle (tâche), entrée, schéma de sortie attendu, réponse scriptée
    (pour l'adaptateur simulé) et vérité terrain facultative (qualité d'extraction)."""

    case_id: str
    role: str
    prompt: str
    input_data: dict[str, Any]
    response_model: Type[BaseModel]
    scripted: Any
    expected_entities: Optional[list[dict[str, Any]]] = None


# Jeu de cas embarqué, déterministe et rejouable hors ligne (T8.10 : comparer fournisseurs,
# versions, modèles et instructions sans dépendre d'un seul prestataire).
EVAL_CASES: list[EvalCase] = [
    EvalCase(
        case_id="plan-1",
        role="planning",
        prompt="Décomposer l'objectif en sous-objectifs et requêtes source",
        input_data={"objective": "Vérifier l'existence d'ACME", "title": "ACME"},
        response_model=PlanProposal,
        scripted={"sub_objectives": ["Identifier ACME"], "source_queries": ["ACME siren"], "reasoning": "recherche par raison sociale"},
    ),
    EvalCase(
        case_id="extract-1",
        role="extraction",
        prompt="Extraire entités et relations du contenu collecté",
        input_data={"content": "ACME SAS, SIREN 123456789, siège à Paris."},
        response_model=Extraction,
        scripted={"entities": [{"kind": "entreprise", "name": "ACME", "identifiers": {"siren": "123456789"}}], "relations": []},
        expected_entities=[{"name": "ACME", "identifiers": {"siren": "123456789"}}],
    ),
    EvalCase(
        case_id="synth-1",
        role="synthesis",
        prompt="Synthétiser et évaluer l'objectif",
        input_data={"objective": "Vérifier l'existence d'ACME", "findings": ["ACME, SIREN 123456789"]},
        response_model=Synthesis,
        scripted={"conclusion": "ACME existe", "support": "documenté", "objective_sufficiently_supported": True},
    ),
]


def _entity_key(name: str, identifiers: dict[str, str]) -> tuple:
    return (name, tuple(sorted(identifiers.items())))


def extraction_metrics(predicted: list, expected: list[dict[str, Any]]) -> dict[str, float]:
    """Précision/rappel/F1 sur les entités (nom + identifiants) — qualité d'extraction (T8.10)."""
    pred = {_entity_key(e.name, e.identifiers) for e in predicted}
    exp = {_entity_key(e["name"], e.get("identifiers", {})) for e in expected}
    tp = len(pred & exp)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(exp) if exp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "predicted": len(pred), "expected": len(exp)}


async def run_case(adapter: AIAdapter, case: EvalCase) -> dict[str, Any]:
    """Exécute un cas et mesure : conformité schéma, erreur, latence, coût, qualité d'extraction."""
    started = time.monotonic()
    base = {
        "case_id": case.case_id,
        "role": case.role,
        "cost_cents": adapter.cost_per_call_cents if adapter.paid else 0,
    }
    try:
        output = await adapter.complete(case.role, case.prompt, case.input_data, case.response_model)
    except ValidationError as exc:
        return {**base, "schema_ok": False, "error": f"conformite_schema:{exc.error_count()}", "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:
        return {**base, "schema_ok": False, "error": f"erreur:{type(exc).__name__}", "latency_ms": int((time.monotonic() - started) * 1000)}
    result: dict[str, Any] = {**base, "schema_ok": True, "error": None, "latency_ms": int((time.monotonic() - started) * 1000)}
    if case.expected_entities is not None and isinstance(output, Extraction):
        result["extraction"] = extraction_metrics(output.entities, case.expected_entities)
    return result


async def evaluate_adapter(adapter_key: str, adapter: AIAdapter, cases: Optional[list[EvalCase]] = None) -> dict[str, Any]:
    """Évalue un adaptateur sur le jeu de cas (exécution séquentielle, déterministe) et produit
    le relevé de résultats : par cas, agrégé par rôle (tâche) et totaux."""
    cases = list(cases) if cases is not None else list(EVAL_CASES)
    results = [await run_case(adapter, case) for case in cases]
    by_role: dict[str, dict[str, Any]] = {}
    for case, res in zip(cases, results):
        agg = by_role.setdefault(case.role, {"cases": 0, "schema_ok": 0, "errors": 0, "latency_ms_total": 0, "cost_cents_total": 0, "extraction_f1_total": 0.0, "extraction_cases": 0})
        agg["cases"] += 1
        agg["schema_ok"] += 1 if res["schema_ok"] else 0
        agg["errors"] += 0 if res["schema_ok"] else 1
        agg["latency_ms_total"] += res["latency_ms"]
        agg["cost_cents_total"] += res["cost_cents"]
        if "extraction" in res:
            agg["extraction_f1_total"] += res["extraction"]["f1"]
            agg["extraction_cases"] += 1
    for agg in by_role.values():
        agg["schema_conformance_rate"] = agg["schema_ok"] / agg["cases"] if agg["cases"] else 0.0
        agg["mean_latency_ms"] = agg["latency_ms_total"] / agg["cases"] if agg["cases"] else 0
        agg["extraction_f1"] = agg["extraction_f1_total"] / agg["extraction_cases"] if agg["extraction_cases"] else None
    n = len(results)
    ok = sum(1 for r in results if r["schema_ok"])
    f1s = [r["extraction"]["f1"] for r in results if "extraction" in r]
    return {
        "adapter": adapter_key,
        "provider": adapter.provider,
        "model": adapter.model,
        "paid": adapter.paid,
        "cases": results,
        "by_role": by_role,
        "totals": {
            "cases": n,
            "schema_conformance_rate": ok / n if n else 0.0,
            "errors": n - ok,
            "mean_latency_ms": sum(r["latency_ms"] for r in results) / n if n else 0,
            "total_cost_cents": sum(r["cost_cents"] for r in results),
            "extraction_f1": sum(f1s) / len(f1s) if f1s else None,
        },
    }


def scripted_adapter_for_cases(cases: list[EvalCase], key: str = "simulated") -> SimulatedAIAdapter:
    """Construit l'adaptateur simulé rejouant exactement les réponses scriptées des cas
    (hors ligne, déterministe, aucune dépense — T3.14/T8.10)."""
    scripted: dict[str, list[Any]] = {}
    for case in cases:
        scripted.setdefault(case.role, []).append(case.scripted)
    return SimulatedAIAdapter(provider=key, model=f"{key}-eval", scripted=scripted)
