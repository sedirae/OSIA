"""Audit #17 — tranche 15 : F05 (routage réel des sources), F06 (contexte de preuves et
schémas IA), F09 (cache complet).

F05 : les tâches plan/rebond ne codent plus `simulated.web` en dur ; les propositions typées
sont validées contre le registre, la sélection par défaut se fait sur les capacités enregistrées
(connecteurs réels préférés, simulation visible et réservée au mode démo) ; un connecteur/fournisseur
demandé mais indisponible produit une erreur explicite (PolicyDeny / ConfigError).

F06 : l'entrée de synthèse contient preuves (id stables), assertions, relations, décisions
humaines et contradictions, bornées ; le JSON Schema du response_model est transmis dans le
prompt par le courtier ; `decisive_proof_ids` est résolu en priorité sur les id de preuves.

F09 : un hit cache suit le même traitement métier qu'une collecte (preuve rattachée, extraction,
tâche de synthèse) sans nouvel appel externe, en conservant la provenance d'origine.
"""

import pytest

from osia.models import PolicyDeny
from osia.tasks import TaskContext, handle_plan, handle_source_query, handle_synthesize

from conftest import make_investigation


async def _branch(engine, inv):
    return (await engine.repo.list_branches(inv["id"]))[0]


async def _insert(engine, inv, branch_id, kind, payload, depth=0, priority=10):
    return await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branch_id, kind=kind, payload=payload, depth=depth, priority=priority
    )


# ---------- F05 : routage réel des sources ----------


async def test_f05_plan_selections_typees_routées_vers_connecteur_retenu(engine):
    """Les propositions typées du plan (connector_id/query/params) sont routées vers le
    connecteur retenu, après validation backend contre le registre."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    engine.broker.adapters["simulated"].scripted = {
        "planning": {
            "sub_objectives": ["so1"],
            "selections": [
                {"connector_id": "gouv.recherche-entreprises", "query": "EDF", "params": {"per_page": 5}, "rationale": "registre entreprises"}
            ],
        }
    }
    task = await _insert(engine, inv, branch["id"], "plan", {"objective": inv["objective"]})
    out = await handle_plan(task, TaskContext(engine=engine))
    sq = [t for t in await engine.repo.list_tasks(inv["id"]) if t["kind"] == "source_query"]
    assert len(sq) == 1
    assert sq[0]["payload"]["connector_id"] == "gouv.recherche-entreprises"
    assert sq[0]["payload"]["params"] == {"per_page": 5}
    assert sq[0]["payload"]["simulated"] is False
    assert out["source_tasks"][0]["connector_id"] == "gouv.recherche-entreprises"


async def test_f05_plan_sans_selections_selection_par_capacites_pas_de_simulated_en_dur(engine):
    """Sans proposition typée, la sélection par capacités choisit un connecteur RÉEL actif
    (web.url, capacité fetch_public_url) — jamais simulated.web en fonctionnement normal."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    engine.broker.adapters["simulated"].scripted = {"planning": {"source_queries": ["requete-1"]}}
    task = await _insert(engine, inv, branch["id"], "plan", {"objective": inv["objective"]})
    await handle_plan(task, TaskContext(engine=engine))
    sq = [t for t in await engine.repo.list_tasks(inv["id"]) if t["kind"] == "source_query"]
    assert sq and sq[0]["payload"]["connector_id"] == "web.url"
    assert sq[0]["payload"]["simulated"] is False


async def test_f05_plan_selection_ia_invalide_rejetee_et_remplacee_par_capacites(engine):
    """Une proposition IA vers un connecteur inconnu ne fait pas échouer le plan : événement
    `plan.selection_rejected` + repli sur la sélection par capacités."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    engine.broker.adapters["simulated"].scripted = {
        "planning": {"selections": [{"connector_id": "inexistant.x", "query": "q1"}]}
    }
    task = await _insert(engine, inv, branch["id"], "plan", {"objective": inv["objective"]})
    await handle_plan(task, TaskContext(engine=engine))
    sq = [t for t in await engine.repo.list_tasks(inv["id"]) if t["kind"] == "source_query"]
    assert sq and sq[0]["payload"]["connector_id"] == "web.url"
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "plan.selection_rejected" for e in events)


async def test_f05_connecteur_demande_indisponible_erreur_explicite_sans_repli(engine):
    """Un connecteur explicitement demandé mais indisponible -> PolicyDeny explicite
    (désactivé = connecteur_demande_indisponible, inconnu = connecteur_inconnu)."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    ctx = TaskContext(engine=engine)
    engine.registry.set_enabled("web.url", False)
    task = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "web.url", "query": "q"})
    with pytest.raises(PolicyDeny) as exc:
        await handle_source_query(task, ctx)
    assert exc.value.reason == "connecteur_demande_indisponible:web.url"
    task2 = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "nope.x", "query": "q"})
    with pytest.raises(PolicyDeny) as exc2:
        await handle_source_query(task2, ctx)
    assert exc2.value.reason == "connecteur_inconnu:nope.x"


def test_f05_fournisseur_ia_demande_indisponible_erreur_de_configuration(monkeypatch):
    """OSIA_AI_PROVIDER explicite vers un fournisseur indisponible -> ConfigError (jamais de
    repli silencieux sur simulated) ; sans explicitation, le repli dev reste autorisé."""
    from osia.ai.real import build_ai_adapters
    from osia.config import ConfigError, Settings

    monkeypatch.delenv("OSIA_MISTRAL_API_KEY", raising=False)
    strict = Settings(ai_provider="mistral", ai_provider_explicit=True)
    with pytest.raises(ConfigError):
        build_ai_adapters(strict, None)
    dev = Settings(ai_provider="mistral", ai_provider_explicit=False)
    _adapters, role_models, _domains = build_ai_adapters(dev, None)
    assert role_models["planning"] == "simulated"


async def test_f05_rebonds_synthese_routés_par_capacites(engine):
    """Les follow-ups de synthèse ne codent plus simulated.web en dur."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    engine.broker.adapters["simulated"].scripted = {
        "synthesis": {
            "conclusion": "partiel",
            "support": "à confirmer",
            "objective_sufficiently_supported": False,
            "suggested_followups": ["suivi-1"],
        }
    }
    task = await _insert(engine, inv, branch["id"], "synthesize", {"query": "q"}, depth=0, priority=5)
    out = await handle_synthesize(task, TaskContext(engine=engine))
    assert out.get("rebond") == 1
    sq = [t for t in await engine.repo.list_tasks(inv["id"]) if t["kind"] == "source_query"]
    assert sq and sq[0]["payload"]["connector_id"] == "web.url"
    assert sq[0]["payload"]["simulated"] is False


# ---------- F06 : contexte de preuves et schémas IA ----------


async def test_f06_synthese_recoit_contexte_borne_et_schema_dans_le_prompt(engine):
    """L'entrée de synthèse contient preuves (id stables), assertions, relations, décisions et
    contradictions ; le prompt transmis à l'adaptateur contient le JSON Schema de sortie."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    proof = await engine.filestore.store_proof(
        investigation_id=inv["id"],
        content=b'{"a": 1}',
        source_url="https://example.test/p1",
        media_type="application/json",
        label="l1",
        connector_id="simulated.web",
    )
    adapter = engine.broker.adapters["simulated"]
    adapter.scripted = {
        "synthesis": {
            "conclusion": "ACME existe",
            "support": "documenté",
            "decisive_proof_ids": [proof["proof_ref_id"]],
            "objective_sufficiently_supported": True,
        }
    }
    task = await _insert(engine, inv, branch["id"], "synthesize", {"query": "q"}, depth=0, priority=5)
    await handle_synthesize(task, TaskContext(engine=engine))
    call = adapter.calls[-1]
    assert call["role"] == "synthesis"
    assert call["input"]["proofs"][0]["id"] == proof["proof_ref_id"]
    assert call["input"]["proofs"][0]["source_url"] == "https://example.test/p1"
    for key in ("assertions", "relations", "decisions", "contradictions", "branch_id"):
        assert key in call["input"]
    assert "JSON Schema" in call["prompt"] and "decisive_proof_ids" in call["prompt"]
    # id de preuve stable résolu en proof_ids de l'assertion décisive
    decisive = [a for a in await engine.graph.list_assertions(inv["id"]) if a["decisive"]]
    assert decisive and decisive[0]["proof_ids"] == [proof["proof_ref_id"]]


async def test_f06_decisive_proof_ids_invente_rejete_decisive_sources_url_repli(engine):
    """Un decisive_proof_ids inventé est ignoré ; decisive_sources (URL) reste un repli."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    proof = await engine.filestore.store_proof(
        investigation_id=inv["id"],
        content=b"{}",
        source_url="https://example.test/p2",
        media_type="application/json",
        label="l2",
        connector_id="simulated.web",
    )
    engine.broker.adapters["simulated"].scripted = {
        "synthesis": {
            "conclusion": "c",
            "support": "documenté",
            "decisive_proof_ids": ["preuve_inventee"],
            "decisive_sources": ["https://example.test/p2"],
            "objective_sufficiently_supported": True,
        }
    }
    task = await _insert(engine, inv, branch["id"], "synthesize", {"query": "q"}, depth=0, priority=5)
    await handle_synthesize(task, TaskContext(engine=engine))
    decisive = [a for a in await engine.graph.list_assertions(inv["id"]) if a["decisive"]]
    assert decisive and decisive[0]["proof_ids"] == [proof["proof_ref_id"]]


# ---------- F09 : cache complet ----------


async def test_f09_cache_hit_produit_preuve_extraction_et_synthese_sans_nouvel_appel(engine):
    """Deux exécutions de la même requête : un seul fetch externe, mais preuve rattachée,
    extraction IA et tâche de synthèse dans CHAQUE investigation (même traitement métier)."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    ctx = TaskContext(engine=engine)
    connector = engine.registry.get("simulated.web")
    adapter = engine.broker.adapters["simulated"]
    adapter.scripted = {"extraction": {"entities": [], "relations": []}}
    task = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "simulated.web", "query": "q-cache"})
    out1 = await handle_source_query(task, ctx)
    assert out1.get("cached") is not True
    assert connector.calls == ["q-cache"]
    adapter.calls.clear()
    out2 = await handle_source_query(task, ctx)
    assert out2["cached"] is True
    assert connector.calls == ["q-cache"]  # aucun second appel externe (B-ACC-06)
    # F09 : le hit suit le même traitement métier qu'une collecte
    proofs = await engine.repo.list_proof_refs(inv["id"])
    assert len(proofs) == 2  # une preuve rattachée par exécution
    assert proofs[0]["proof_sha256"] == proofs[1]["proof_sha256"] == out2["proof_sha256"]
    assert any(c["role"] == "extraction" for c in adapter.calls)  # extraction rejouée sur le hit
    synth = [t for t in await engine.repo.list_tasks(inv["id"]) if t["kind"] == "synthesize"]
    assert len(synth) == 2  # une tâche de synthèse par exécution
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "discovery" and (e.payload or {}).get("cached") for e in events)


async def test_f09_deux_investigations_meme_requete_resultats_dans_chacune(engine):
    """Recette F09 : deux investigations distinctes sur la même requête — un seul téléchargement,
    mais preuves et résultats corrects dans chacune."""
    ctx = TaskContext(engine=engine)
    connector = engine.registry.get("simulated.web")
    engine.broker.adapters["simulated"].scripted = {"extraction": {"entities": [], "relations": []}}
    inv1 = await make_investigation(engine, title="inv1")
    inv2 = await make_investigation(engine, title="inv2")
    b1 = await _branch(engine, inv1)
    b2 = await _branch(engine, inv2)
    t1 = await _insert(engine, inv1, b1["id"], "source_query", {"connector_id": "simulated.web", "query": "q-partagee"})
    t2 = await _insert(engine, inv2, b2["id"], "source_query", {"connector_id": "simulated.web", "query": "q-partagee"})
    await handle_source_query(t1, ctx)
    out2 = await handle_source_query(t2, ctx)
    assert out2["cached"] is True
    assert connector.calls == ["q-partagee"]  # un seul téléchargement
    assert len(await engine.repo.list_proof_refs(inv1["id"])) == 1
    assert len(await engine.repo.list_proof_refs(inv2["id"])) == 1  # preuve aussi dans la 2e
    assert len([t for t in await engine.repo.list_tasks(inv2["id"]) if t["kind"] == "synthesize"]) == 1
