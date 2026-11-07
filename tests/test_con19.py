"""CON-19 (T3.14, T8.10) : jeux de recette rejouables hors ligne, CI et métriques d'évaluation
IA par tâche.

Vérifications : scénarios de bout en bout rejoués avec connecteur + IA SIMULÉS (aucun appel
réseau, aucune dépense) produisant des relevés de résultats réels ; cas de panne (source
indisponible, sortie IA non conforme, arrêt utilisateur) et isolation entre investigations ;
évaluation par tâche (conformité schéma, erreurs, latence, coût, F1 d'extraction) reproductible
sur adaptateur simulé ; workflow CI présent et câblé sur les PR."""

import json
import pathlib

import pytest

from osia.ai.eval import EVAL_CASES, EvalCase, evaluate_adapter, extraction_metrics, scripted_adapter_for_cases
from osia.ai.schemas import Extraction
from osia.recette import SCENARIOS, run_all, run_scenario


# ---------- Jeux de recette hors ligne (T3.14) ----------


async def test_recette_happy_path_releve_reel(engine):
    """Scénario nominal de bout en bout, hors ligne : relevé avec état final, tâches, preuves,
    événements et entrées du journal technique (T3.13)."""
    releve = await run_scenario(engine, "happy_path")
    assert releve["scenario"] == "happy_path"
    assert releve["offline"] is True
    assert releve["final_state"] == "stopped"
    assert releve["stop_reason"] == "objective_suffisamment_etaye"
    kinds = {t["kind"]: t["state"] for t in releve["tasks"]}
    assert kinds.get("plan") == "succeeded"
    assert kinds.get("source_query") == "succeeded"
    assert kinds.get("synthesize") == "succeeded"
    assert releve["proofs"] >= 1
    assert releve["entities"] == ["ACME"]
    assert "discovery" in releve["events"]
    assert "source.query" in releve["techlog_events"]  # journal technique câblé (CON-18)
    assert releve["source_calls"] == ["requete-1"]  # un seul appel source simulé
    assert isinstance(releve["duration_ms"], int) and releve["duration_ms"] >= 0
    assert releve["budget"] is not None
    assert isinstance(releve["budget"], dict)  # BudgetView sérialisé en objet JSON exploitable
    json.dumps(releve, default=str)  # relevé sérialisable


async def test_recette_source_indisponible_ne_casse_pas_tout(engine):
    """Une source défaillante ne provoque pas l'échec brutal : tâche en échec classifié,
    opération incertaine journalisée, relevé produit quand même (T3.14)."""
    releve = await run_scenario(engine, "source_indisponible")
    sq = [t for t in releve["tasks"] if t["kind"] == "source_query"]
    assert sq and sq[0]["state"] == "failed"
    assert "source_indisponible" in (sq[0]["error"] or "")
    assert "op.uncertain" in releve["events"]
    assert releve["final_state"] in ("stopped", "error")


async def test_recette_sortie_ia_invalide_rejetee(engine):
    """T8.6 : une sortie IA non conforme au schéma est rejetée (tâche failed, op.failed)."""
    releve = await run_scenario(engine, "sortie_ia_invalide")
    sq = [t for t in releve["tasks"] if t["kind"] == "source_query"]
    assert sq and sq[0]["state"] == "failed"
    assert "sortie_ia_invalide" in (sq[0]["error"] or "")
    assert "op.failed" in releve["events"]


async def test_recette_arret_utilisateur(engine):
    """Arrêt utilisateur : suspension propre, stop_reason utilisateur (T3.14 interruptions)."""
    from osia.models import StopReason

    releve = await run_scenario(engine, "arret_utilisateur")
    assert releve["final_state"] == "stopped"
    assert releve["stop_reason"] == StopReason.USER.value


async def test_recette_isolation_entre_investigations(engine):
    """Isolation : deux investigations rejouées à la suite ont des entités disjointes (T3.14)."""
    releve = await run_scenario(engine, "isolation")
    iso = releve["isolation"]
    assert iso["investigation_1_entities"] == ["ACME"]
    assert iso["investigation_2_entities"] == ["ZENITH"]
    assert iso["separated"] is True


async def test_recette_run_all_rejouable(engine):
    """Tous les scénarios rejoués dans l'ordre déterministe, relevés par scénario. Chaque
    scénario produit son résultat attendu DANS le lot (le cache source B-ACC-06 est
    réinitialisé entre scénarios : un hit cache court-circuiterait la chaîne)."""
    releves = await run_all(engine)
    assert sorted(releves.keys()) == sorted(SCENARIOS.keys())
    for name, releve in releves.items():
        assert releve["scenario"] == name
        assert releve["offline"] is True
        json.dumps(releve, default=str)
    assert releves["happy_path"]["stop_reason"] == "objective_suffisamment_etaye"
    assert releves["happy_path"]["proofs"] >= 1
    assert releves["arret_utilisateur"]["stop_reason"] == "user_interrupt"
    assert releves["isolation"]["isolation"]["separated"] is True


async def test_recette_moteur_non_demarre_erreur_propre(engine):
    """Edge case : manage_engine=False sur un moteur non démarré -> erreur explicite plutôt
    qu'un relevé dégénéré (tâches bloquées, arrêt forcé après timeout)."""
    with pytest.raises(RuntimeError, match="moteur non démarré"):
        await run_scenario(engine, "happy_path", manage_engine=False)


# ---------- Évaluation IA par tâche (T8.10) ----------


async def test_eval_simule_conforme_et_reproductible():
    """Jeu de cas embarqué rejoué sur adaptateur simulé : conformité schéma 100 %, F1
    d'extraction 1.0, coût 0 (hors ligne), métriques par rôle présentes."""
    adapter = scripted_adapter_for_cases(EVAL_CASES)
    report1 = await evaluate_adapter("simulated", adapter)
    adapter2 = scripted_adapter_for_cases(EVAL_CASES)
    report2 = await evaluate_adapter("simulated", adapter2)
    assert report1["totals"]["cases"] == len(EVAL_CASES)
    assert report1["totals"]["schema_conformance_rate"] == 1.0
    assert report1["totals"]["errors"] == 0
    assert report1["totals"]["total_cost_cents"] == 0  # simulé : aucune dépense
    assert report1["totals"]["extraction_f1"] == 1.0
    assert set(report1["by_role"].keys()) == {"planning", "extraction", "synthesis"}
    assert report1["by_role"]["extraction"]["extraction_f1"] == 1.0
    # reproductible : deux exécutions identiques (hors latences) donnent les mêmes métriques
    assert report1["totals"]["schema_conformance_rate"] == report2["totals"]["schema_conformance_rate"]
    assert report1["totals"]["extraction_f1"] == report2["totals"]["extraction_f1"]
    for case in report1["cases"]:
        assert case["schema_ok"] is True and case["error"] is None
        assert isinstance(case["latency_ms"], int) and case["latency_ms"] >= 0


async def test_eval_sortie_invalide_comptee_comme_non_conforme():
    """T8.6 : un cas dont la réponse scriptée viole le schéma est compté non conforme."""
    cases = [
        EvalCase(
            case_id="extract-bad",
            role="extraction",
            prompt="Extraire",
            input_data={"content": "x"},
            response_model=Extraction,
            scripted={"entities": "oops"},  # invalide
            expected_entities=[{"name": "X", "identifiers": {}}],
        )
    ]
    report = await evaluate_adapter("simulated", scripted_adapter_for_cases(cases), cases)
    assert report["totals"]["schema_conformance_rate"] == 0.0
    assert report["totals"]["errors"] == 1
    assert report["cases"][0]["schema_ok"] is False
    assert "conformite_schema" in report["cases"][0]["error"]


def test_extraction_metrics_precision_rappel_f1():
    class E:
        def __init__(self, name, identifiers):
            self.name = name
            self.identifiers = identifiers

    m = extraction_metrics([E("ACME", {"siren": "1"}), E("GHOST", {})], [{"name": "ACME", "identifiers": {"siren": "1"}}])
    assert m["precision"] == 0.5 and m["recall"] == 1.0 and abs(m["f1"] - 2 / 3) < 1e-9
    m2 = extraction_metrics([], [{"name": "ACME", "identifiers": {}}])
    assert m2["recall"] == 0.0 and m2["f1"] == 0.0


# ---------- CI (T3.14 : tests intégrables aux processus CI) ----------


def test_workflow_ci_present_et_cable_sur_pr():
    wf = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    assert wf.exists(), "workflow CI manquant (.github/workflows/ci.yml)"
    text = wf.read_text(encoding="utf-8")
    assert "pull_request" in text  # déclenché sur les revues de code
    assert "pytest" in text  # exécute la suite de tests
    assert "ubuntu-latest" in text
