"""Audit #17 — tranche 16 : F07 (étayage : confiance connecteur vs source primaire) et
F08 (orchestration : branche autonome, pause/reprise, terminaison explicite, pistes non lancées).

F07 : `objective_etaye` exige une PREUVE DIRECTE (proof_ids résolubles) ; une source primaire
est un connecteur dont le manifeste déclare `primary_source=True` (jamais un simple
trust_level 'official' — web.url/simulated.web ne sont pas primaires) ; l'indépendance se
mesure aux DOMAINES des URLs (pas au nombre de connecteurs) ; assertions rejetées/non établies
exclues ; contradictions majeures non résolues bloquantes.

F08 : branche explicite sur investigation arrêtée la réactive et s'exécute ; suspend marque les
tâches 'interrupted' (re-mises en file par resume) et non 'cancelled' ; le plan utilise
l'objectif de la branche ; épuisement -> état terminal 'work_exhausted' ; pistes non lancées
restituées en limite de profondeur.
"""

import pytest

from osia.connectors.simulated import SimulatedConnector
from osia.models import ClaimNature, CreateBranchRequest, PolicyDeny, StopReason, SupportLevel
from osia.tasks import TaskContext, handle_plan, handle_synthesize

from conftest import make_investigation


async def _branch(engine, inv):
    return (await engine.repo.list_branches(inv["id"]))[0]


def _register_primary(engine, cid="simulated.registre"):
    c = SimulatedConnector(cid)
    c.manifest.primary_source = True
    engine.registry.register(c)
    return c


async def _proof(engine, inv, url, connector_id):
    return await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"{}", source_url=url, connector_id=connector_id
    )


async def _decisive(engine, inv, branch_id, proof_ids, support=SupportLevel.DOCUMENTE):
    return await engine.graph.add_assertion(
        inv["id"], branch_id=branch_id, statement="réponse", nature=ClaimNature.CONCLUSION_ANALYTIQUE,
        support_level=support, proof_ids=proof_ids, decisive=True, derivation="ia",
    )


# ---------- F07 ----------


async def test_f07_repro_audit_rejetee_non_etabli_web_url_ne_etaye_pas(engine):
    """Repro audit F07 : hypothèse non_etabli + human_decision=rejected + preuve web.url
    (connecteur 'official' mais PAS primaire) -> etaye False."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    proof = await _proof(engine, inv, "https://blog.test/article", "web.url")
    a = await _decisive(engine, inv, branch["id"], [proof["proof_ref_id"]], support=SupportLevel.NON_ETABLI)
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="reject")
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is False
    r = obj["reponses_decisives"][0]
    assert r["rejetee"] is True and r["non_etabli"] is True
    assert r["base"] == "insuffisant"  # web.url : trust official mais primary_source=False


async def test_f07_web_url_official_mais_pas_primaire(engine):
    """Un connecteur 'official' générique (web.url) ne fonde pas à lui seul l'étayage."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    proof = await _proof(engine, inv, "https://example.test/page", "web.url")
    await _decisive(engine, inv, branch["id"], [proof["proof_ref_id"]])
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is False
    assert obj["reponses_decisives"][0]["base"] == "insuffisant"
    assert obj["reponses_decisives"][0]["niveaux_confiance"] == {"web.url": "official"}


async def test_f07_source_primaire_manifeste_etaye(engine):
    """Un registre déclaré primary_source=True fonde 'source_primaire'."""
    _register_primary(engine)
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    proof = await _proof(engine, inv, "https://registre.test/fiche", "simulated.registre")
    await _decisive(engine, inv, branch["id"], [proof["proof_ref_id"]])
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is True
    assert obj["reponses_decisives"][0]["base"] == "source_primaire"


async def test_f07_deux_connecteurs_meme_domaine_pas_independants(engine):
    """F07 : deux connecteurs distincts sur le MÊME domaine ne prouvent pas l'indépendance
    (l'ancien critère len(connecteurs) >= 2 était insuffisant)."""
    p1 = SimulatedConnector("simulated.press.a")
    p2 = SimulatedConnector("simulated.press.b")
    engine.registry.register(p1)
    engine.registry.register(p2)
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    a = await _proof(engine, inv, "https://media.test/article-1", "simulated.press.a")
    b = await _proof(engine, inv, "https://media.test/article-2", "simulated.press.b")
    await _decisive(engine, inv, branch["id"], [a["proof_ref_id"], b["proof_ref_id"]], support=SupportLevel.CORROBORE)
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is False
    assert obj["reponses_decisives"][0]["base"] == "insuffisant"
    assert obj["reponses_decisives"][0]["domaines"] == ["media.test"]


async def test_f07_deux_domaines_distincts_independants(engine):
    p1 = SimulatedConnector("simulated.press.a")
    p2 = SimulatedConnector("simulated.press.b")
    engine.registry.register(p1)
    engine.registry.register(p2)
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    a = await _proof(engine, inv, "https://media-a.test/1", "simulated.press.a")
    b = await _proof(engine, inv, "https://media-b.test/2", "simulated.press.b")
    await _decisive(engine, inv, branch["id"], [a["proof_ref_id"], b["proof_ref_id"]], support=SupportLevel.CORROBORE)
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is True
    assert obj["reponses_decisives"][0]["base"] == "deux_sources_independantes"


async def test_f07_preuve_directe_requise_et_rejetee_exclue(engine):
    """proof_ids vers une preuve inexistante -> pas de preuve directe -> non étayé ;
    assertion rejetée avec preuve primaire -> non étayé."""
    _register_primary(engine)
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    await _decisive(engine, inv, branch["id"], ["preuve_inexistante"])
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is False
    assert obj["reponses_decisives"][0]["preuve_directe"] is False

    inv2 = await make_investigation(engine, title="rejetée")
    branch2 = await _branch(engine, inv2)
    proof = await _proof(engine, inv2, "https://registre.test/f", "simulated.registre")
    a = await _decisive(engine, inv2, branch2["id"], [proof["proof_ref_id"]])
    await engine.graph.decide(inv2["id"], target_type="assertion", target_id=a["id"], action="reject")
    obj2 = await engine.graph.objective_etaye(inv2["id"], branch2["id"])
    assert obj2["etaye"] is False
    assert obj2["reponses_decisives"][0]["rejetee"] is True


# ---------- F08 ----------


async def test_f08_branche_explicite_reactive_investigation_arignee_et_execute(engine):
    """Branche créée après arrêt du parent : l'investigation est réactivée et la tâche plan
    de la branche est claimable (elle s'exécute)."""
    inv = await make_investigation(engine)
    await engine.orchestrator.stop(inv["id"], StopReason.USER)
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "stopped"
    branch = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="approfondir", explicit_acceptance=True)
    )
    inv2 = await engine.repo.get_investigation(inv["id"])
    assert inv2["state"] == "running" and inv2["stop_reason"] is None
    assert branch["state"] == "running"
    claimed = await engine.repo.claim_next_task()
    assert claimed is not None and claimed["branch_id"] == branch["id"] and claimed["kind"] == "plan"
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "investigation.reactivated" for e in events)


async def test_f08_branche_sur_investigation_suspendue_refusee(engine):
    inv = await make_investigation(engine)
    await engine.orchestrator.suspend(inv["id"])
    with pytest.raises(PolicyDeny) as exc:
        await engine.orchestrator.create_branch(
            inv["id"], CreateBranchRequest(objective="x", explicit_acceptance=True)
        )
    assert "reprise_requise" in exc.value.reason


async def test_f08_suspend_interrompt_et_resume_remet_en_file(engine):
    """Une pause avant exécution ne perd pas le travail : queued -> interrupted (pas cancelled),
    branches suspendues, puis resume() remet en file."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branch["id"], kind="noop", payload={}
    )
    await engine.orchestrator.suspend(inv["id"])
    assert (await engine.repo.get_task(task["id"]))["state"] == "interrupted"
    assert (await engine.repo.get_branch(branch["id"]))["state"] == "suspended"
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "suspended"
    assert await engine.repo.claim_next_task() is None  # rien n'est claimé en pause
    await engine.orchestrator.resume(inv["id"])
    assert (await engine.repo.get_task(task["id"]))["state"] == "queued"
    assert (await engine.repo.get_branch(branch["id"]))["state"] == "running"
    assert (await engine.repo.get_investigation(inv["id"]))["state"] == "running"


async def test_f08_plan_utilise_objectif_de_la_branche(engine):
    inv = await make_investigation(engine, objective="objectif parent")
    branch = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="OBJECTIF-BRANCHE", explicit_acceptance=True)
    )
    engine.broker.adapters["simulated"].scripted = {"planning": {"source_queries": []}}
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branch["id"], kind="plan", payload={"objective": "OBJECTIF-BRANCHE"}, depth=0, priority=100
    )
    await handle_plan(task, TaskContext(engine=engine))
    call = engine.broker.adapters["simulated"].calls[-1]
    assert call["input"]["objective"] == "OBJECTIF-BRANCHE"
    assert call["input"]["branch_id"] == branch["id"]


async def test_f08_epuisement_termine_explicitement(engine):
    """Plus aucune tâche exécutable -> état terminal 'work_exhausted' (succès et échec)."""
    inv = await make_investigation(engine)
    plan_task = (await engine.repo.list_tasks(inv["id"]))[0]
    await engine.repo.set_task_state(plan_task["id"], "succeeded", finished=True)
    await engine.orchestrator.on_task_succeeded(plan_task, {})
    final = await engine.repo.get_investigation(inv["id"])
    assert final["state"] == "stopped" and final["stop_reason"] == StopReason.EXHAUSTED.value

    inv2 = await make_investigation(engine, title="échec")
    plan2 = (await engine.repo.list_tasks(inv2["id"]))[0]
    await engine.repo.set_task_state(plan2["id"], "failed", error="boom", finished=True)
    await engine.orchestrator.on_task_failed(plan2, "boom")
    final2 = await engine.repo.get_investigation(inv2["id"])
    assert final2["state"] == "stopped" and final2["stop_reason"] == StopReason.EXHAUSTED.value


async def test_f08_pistes_non_lancees_restituees_en_limite_de_profondeur(engine):
    inv = await make_investigation(engine, limits={"max_rebonds": 1})
    branch = await _branch(engine, inv)
    engine.broker.adapters["simulated"].scripted = {
        "synthesis": {
            "conclusion": "partiel",
            "support": "à confirmer",
            "suggested_followups": ["piste-1", "piste-2"],
            "objective_sufficiently_supported": False,
        }
    }
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branch["id"], kind="synthesize", payload={"query": "q"}, depth=1, priority=5
    )
    out = await handle_synthesize(task, TaskContext(engine=engine))
    assert out["stop"] == "depth_limit"
    assert out["followups_non_lancees"] == ["piste-1", "piste-2"]
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "synthesis.followups_non_lances" for e in events)
    final = await engine.repo.get_investigation(inv["id"])
    assert final["stop_reason"] == StopReason.DEPTH_LIMIT.value
