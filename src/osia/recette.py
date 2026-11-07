"""CON-19 / T3.14 : jeux de recette REJOUABLES HORS LIGNE.

Chaque scénario exécute une investigation de bout en bout avec le connecteur et l'adaptateur IA
**simulés** (fixtures déterministes, aucune dépense API, aucun appel réseau) et produit un
**relevé de résultats réels** : état final, stop_reason, tâches par état, preuves, entités,
événements, budget consommé et entrées du journal technique (T3.13).

Scénarios : happy_path, source_indisponible, sortie_ia_invalide, arret_utilisateur, isolation.
CLI : `osia recette run [--scenario NOM|all] [--out DIR]`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from .models import CreateInvestigationRequest, StopReason

# Jeux de recette déterministes. `scripted` = réponses de l'adaptateur IA simulé par rôle
# (une liste est dépilée dans l'ordre des appels) ; `fixtures` = réponses du connecteur simulé ;
# `fail_on` = requêtes simulant une source indisponible.
SCENARIOS: dict[str, dict[str, Any]] = {
    "happy_path": {
        "title": "recette happy path",
        "objective": "Vérifier ACME",
        "scripted": {
            "planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
            "extraction": {"entities": [{"kind": "entreprise", "name": "ACME", "identifiers": {"siren": "123456789"}}], "relations": []},
            "synthesis": {"conclusion": "ACME existe", "support": "documenté", "decisive_sources": ["https://example.test/simulated?q=requete-1"], "objective_sufficiently_supported": True},
        },
        "fixtures": {"requete-1": {"query": "requete-1", "results": [{"name": "ACME", "siren": "123456789"}]}},
    },
    "source_indisponible": {
        "title": "recette source indisponible",
        "objective": "Vérifier ACME",
        "scripted": {
            "planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
            "extraction": {"entities": [], "relations": []},
            "synthesis": {"conclusion": "source indisponible", "support": "non établi", "objective_sufficiently_supported": False},
        },
        "fixtures": {},
        "fail_on": {"requete-1"},
    },
    "sortie_ia_invalide": {
        "title": "recette sortie IA invalide",
        "objective": "Vérifier ACME",
        "scripted": {
            "planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
            "extraction": {"entities": "oops-pas-une-liste"},  # non conforme au schéma (T8.6)
            "synthesis": {"conclusion": "n/a", "support": "non établi", "objective_sufficiently_supported": False},
        },
        "fixtures": {"requete-1": {"query": "requete-1", "results": []}},
    },
    "arret_utilisateur": {
        "title": "recette arrêt utilisateur",
        "objective": "Vérifier ACME",
        "scripted": {
            "planning": {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
            "extraction": {"entities": [], "relations": []},
            "synthesis": {"conclusion": "interrompu", "support": "à confirmer", "objective_sufficiently_supported": False},
        },
        "fixtures": {"requete-1": {"query": "requete-1", "results": []}},
        "stop_user": True,
    },
    "isolation": {
        "title": "recette isolation",
        "objective": "Vérifier ACME puis ZENITH",
        "scripted": {
            # requêtes distinctes par investigation : pas de hit cache (B-ACC-06) entre les deux
            "planning": [
                {"sub_objectives": ["so1"], "source_queries": ["requete-1"]},
                {"sub_objectives": ["so2"], "source_queries": ["requete-2"]},
            ],
            "extraction": [
                {"entities": [{"kind": "entreprise", "name": "ACME", "identifiers": {"siren": "123456789"}}], "relations": []},
                {"entities": [{"kind": "entreprise", "name": "ZENITH", "identifiers": {"siren": "987654321"}}], "relations": []},
            ],
            "synthesis": {"conclusion": "ok", "support": "documenté", "objective_sufficiently_supported": True},
        },
        "fixtures": {"requete-1": {"query": "requete-1", "results": []}, "requete-2": {"query": "requete-2", "results": []}},
        "second_investigation": True,
    },
}


async def _wait_state(engine, inv_id: str, states: set[str], timeout: float = 15.0):
    for _ in range(int(timeout / 0.05)):
        inv = await engine.repo.get_investigation(inv_id)
        if inv["state"] in states:
            return inv
        await asyncio.sleep(0.05)
    return await engine.repo.get_investigation(inv_id)


async def _wait_tasks_settled(engine, inv_id: str, timeout: float = 3.0) -> None:
    """Laisse les tâches en cours se terminer avant de relever (évite les états transitoires)."""
    for _ in range(int(timeout / 0.05)):
        tasks = await engine.repo.list_tasks(inv_id)
        if all(t["state"] not in ("queued", "running") for t in tasks):
            return
        await asyncio.sleep(0.05)


async def _releve_investigation(engine, inv_id: str) -> dict[str, Any]:
    inv = await engine.repo.get_investigation(inv_id)
    tasks = await engine.repo.list_tasks(inv_id)
    proofs = await engine.repo.list_proof_refs(inv_id)
    entities = await engine.pool.fetch("SELECT data FROM entities WHERE investigation_id = $1", inv_id)
    events = await engine.repo.list_events(inv_id)
    budget = await engine.budgets.budget_view(inv_id)
    names: list[str] = []
    for row in entities:
        data = row["data"]
        if isinstance(data, str):
            import json as _json

            data = _json.loads(data)
        names.append(data.get("name", "?"))
    return {
        "investigation_id": inv_id,
        "final_state": inv["state"],
        "stop_reason": inv["stop_reason"],
        "tasks": [{"kind": t["kind"], "state": t["state"], "error": t.get("error")} for t in tasks],
        "proofs": len(proofs),
        "entities": sorted(names),
        "events": [e.type for e in events],
        "budget": budget,
    }


async def run_scenario(engine, name: str, timeout: float = 6.0, manage_engine: bool = True) -> dict[str, Any]:
    """Exécute un scénario de bout en bout, HORS LIGNE (simulations uniquement), et retourne
    le relevé de résultats réels de l'exécution. `manage_engine=False` : le moteur est déjà
    démarré (lot de scénarios via `run_all`) et reste en marche."""
    if name not in SCENARIOS:
        raise KeyError(f"scénario inconnu: {name} (disponibles: {', '.join(sorted(SCENARIOS))})")
    spec = SCENARIOS[name]
    adapter = engine.broker.adapters["simulated"]
    adapter.scripted = spec["scripted"]
    adapter.calls.clear()
    connector = engine.registry.get("simulated.web")
    connector.fixtures = spec.get("fixtures", {})
    connector.fail_on = set(spec.get("fail_on", []))
    connector.calls.clear()
    started = time.monotonic()
    if manage_engine:
        await engine.start()
    try:
        inv = await engine.orchestrator.start_investigation(
            CreateInvestigationRequest(title=spec["title"], objective=spec["objective"], profile_id=spec.get("profile_id", "rapide"))
        )
        if spec.get("stop_user"):
            await asyncio.sleep(0.3)  # laisser l'investigation démarrer
            await engine.orchestrator.stop(inv["id"], StopReason.USER)
        final = await _wait_state(engine, inv["id"], {"stopped", "error"}, timeout)
        if final["state"] not in ("stopped", "error"):
            await engine.orchestrator.stop(inv["id"], StopReason.USER)
            final = await engine.repo.get_investigation(inv["id"])
        await _wait_tasks_settled(engine, inv["id"])
        releve = await _releve_investigation(engine, inv["id"])
        if spec.get("second_investigation"):
            inv2 = await engine.orchestrator.start_investigation(
                CreateInvestigationRequest(title=spec["title"] + " (2)", objective=spec["objective"], profile_id="rapide")
            )
            final2 = await _wait_state(engine, inv2["id"], {"stopped", "error"}, timeout)
            if final2["state"] not in ("stopped", "error"):
                await engine.orchestrator.stop(inv2["id"], StopReason.USER)
            await _wait_tasks_settled(engine, inv2["id"])
            releve2 = await _releve_investigation(engine, inv2["id"])
            releve["isolation"] = {
                "investigation_1_entities": releve["entities"],
                "investigation_2_entities": releve2["entities"],
                "separated": set(releve["entities"]).isdisjoint(releve2["entities"]),
            }
    finally:
        if manage_engine:
            engine.scheduler.stop()
            if engine._runner:
                await engine._runner
    releve.update(
        {
            "scenario": name,
            "offline": True,  # connecteur + IA simulés : aucun appel réseau, aucune dépense
            "source_calls": list(connector.calls),
            "ai_calls": [{"role": c["role"]} for c in adapter.calls],
            "techlog_events": [e["event"] for e in engine.techlog.read(limit=500)],
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    )
    return releve


async def run_all(engine, timeout: float = 6.0) -> dict[str, dict[str, Any]]:
    """Rejoue TOUS les scénarios (ordre déterministe) sur un moteur démarré une seule fois,
    et retourne les relevés par scénario."""
    await engine.start()
    try:
        return {name: await run_scenario(engine, name, timeout=timeout, manage_engine=False) for name in sorted(SCENARIOS)}
    finally:
        engine.scheduler.stop()
        if engine._runner:
            await engine._runner
