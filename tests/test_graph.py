import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.connectors.base import TrustLevel
from osia.connectors.simulated import SimulatedConnector
from osia.models import (
    CONFIDENCE_DIMENSIONS,
    ClaimNature,
    ConfidenceLevel,
    MatchBasis,
    PolicyDeny,
    SupportLevel,
)

from conftest import make_investigation


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def first_branch(engine, inv_id):
    return (await engine.repo.list_branches(inv_id))[0]


async def test_exact_identifier_attaches_but_name_alone_does_not_merge(engine):
    inv = await make_investigation(engine)
    a = await engine.graph.upsert_entity(
        inv["id"], kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123 456 789"}
    )
    b = await engine.graph.upsert_entity(
        inv["id"], kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"}
    )
    assert a["matched"] == "created"
    assert b["matched"] == "exact_identifier"
    assert a["entity_id"] == b["entity_id"]
    c = await engine.graph.upsert_entity(
        inv["id"], kind="organisation", data={"name": "ACME"}, identifiers={"lei": "969500LEI00000001"}
    )
    assert c["entity_id"] != a["entity_id"]
    entities = await engine.graph.list_entities(inv["id"])
    assert len(entities) == 2
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "entity.attached" for e in events)


async def test_match_merge_undo_reversible_and_non_destructive(engine):
    inv = await make_investigation(engine)
    a = await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "Jean Dupont"}, identifiers={"passeport": "P1"})
    b = await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "J. Dupont"}, identifiers={"passeport": "P2"})
    prop = await engine.graph.propose_match(
        inv["id"], entity_a=a["entity_id"], entity_b=b["entity_id"],
        basis=MatchBasis.SIMILARITY, justification="nom proche", confidence=ConfidenceLevel.MOYENNE,
    )
    assert prop["status"] == "proposed"
    with pytest.raises(PolicyDeny):
        await engine.graph.propose_match(inv["id"], entity_a=a["entity_id"], entity_b=a["entity_id"])
    merge = await engine.graph.decide(
        inv["id"], target_type="match_proposal", target_id=prop["id"], action="merge", actor="humain"
    )
    row = await engine.pool.fetchrow("SELECT merged_into FROM entities WHERE id = $1", b["entity_id"])
    assert row["merged_into"] == a["entity_id"]
    assert len(await engine.graph.list_entities(inv["id"])) == 1
    assert len(await engine.graph.list_entities(inv["id"], include_merged=True)) == 2
    prop_row = await engine.pool.fetchrow("SELECT status FROM match_proposals WHERE id = $1", prop["id"])
    assert prop_row["status"] == "validated"
    await engine.graph.decide(
        inv["id"], target_type="match_proposal", target_id=prop["id"], action="undo", reverts=merge["id"]
    )
    row = await engine.pool.fetchrow("SELECT merged_into FROM entities WHERE id = $1", b["entity_id"])
    assert row["merged_into"] is None
    prop_row = await engine.pool.fetchrow("SELECT status FROM match_proposals WHERE id = $1", prop["id"])
    assert prop_row["status"] == "proposed"
    events = await engine.repo.list_events(inv["id"])
    types = [e.type for e in events]
    assert "entity.merged" in types and "entity.unmerged" in types and "decision.applied" in types


async def test_reject_match_degrades_dependent_relations_without_deleting(engine):
    inv = await make_investigation(engine)
    a = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "A"}, identifiers={"siren": "1"})
    b = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "B"}, identifiers={"siren": "2"})
    prop = await engine.graph.propose_match(inv["id"], entity_a=a["entity_id"], entity_b=b["entity_id"], basis=MatchBasis.CROSS_REFERENCE)
    rel = await engine.graph.add_relation(
        inv["id"], branch_id=None, src_id=a["entity_id"], dst_id=b["entity_id"], type="capitalise",
        support_level=SupportLevel.CORROBORE, match_proposal_id=prop["id"], derivation="ia",
    )
    await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="reject")
    row = await engine.pool.fetchrow("SELECT * FROM relations WHERE id = $1", rel["id"])
    assert row["support_level"] == "a_confirmer"
    assert row["human_decision"] == "unexamined"
    events = await engine.repo.list_events(inv["id"])
    assert any(e.type == "relation.revaluated" for e in events)
    assert any(e.type == "match.rejected" for e in events)


async def test_contradiction_blocks_objective_until_human_resolution(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    # F07 : seule une source primaire (manifeste primary_source=True) fonde "source_primaire"
    registre = SimulatedConnector("simulated.registre")
    registre.manifest.primary_source = True
    engine.registry.register(registre)
    proof = await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"{}", source_url="https://registre.test/1", connector_id="simulated.registre"
    )
    a = await engine.graph.add_assertion(
        inv["id"], branch_id=branch["id"], statement="ACME est active",
        nature=ClaimNature.FAIT_ETABLI, support_level=SupportLevel.DOCUMENTE,
        proof_ids=[proof["proof_ref_id"]], decisive=True, derivation="source",
    )
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is True
    assert obj["reponses_decisives"][0]["base"] == "source_primaire"
    c = await engine.graph.add_assertion(
        inv["id"], branch_id=branch["id"], statement="ACME est dissoute",
        nature=ClaimNature.INFORMATION_RAPPORTEE, support_level=SupportLevel.CONTRADICTOIRE,
        contradicted_by=[a["id"]],
    )
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is False
    assert obj["contradictions_majeures"]
    orig = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    assert orig["support_level"] == "contradictoire"
    assert c["id"] in (orig["contradicted_by"] if isinstance(orig["contradicted_by"], list) else __import__("json").loads(orig["contradicted_by"]))
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=c["id"], action="validate")
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is True


async def test_objective_needs_primary_or_two_independent_sources(engine):
    press = SimulatedConnector("simulated.press")
    press.manifest.trust_level = TrustLevel.APPROVED
    press2 = SimulatedConnector("simulated.press2")
    press2.manifest.trust_level = TrustLevel.APPROVED
    engine.registry.register(press)
    engine.registry.register(press2)
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    p1 = await engine.filestore.store_proof(investigation_id=inv["id"], content=b"1", source_url="https://a.test/1", connector_id="simulated.press")
    p2 = await engine.filestore.store_proof(investigation_id=inv["id"], content=b"2", source_url="https://b.test/2", connector_id="simulated.press2")
    await engine.graph.add_assertion(
        inv["id"], branch_id=branch["id"], statement="Fait corroboré",
        nature=ClaimNature.FAIT_ETABLI, support_level=SupportLevel.CORROBORE,
        proof_ids=[p1["proof_ref_id"], p2["proof_ref_id"]], decisive=True, derivation="source",
    )
    obj = await engine.graph.objective_etaye(inv["id"], branch["id"])
    assert obj["etaye"] is True
    assert obj["reponses_decisives"][0]["base"] == "deux_sources_independantes"
    inv2 = await make_investigation(engine, title="source unique non officielle")
    branch2 = await first_branch(engine, inv2["id"])
    p3 = await engine.filestore.store_proof(investigation_id=inv2["id"], content=b"3", source_url="https://c.test/3", connector_id="simulated.press")
    await engine.graph.add_assertion(
        inv2["id"], branch_id=branch2["id"], statement="Fait isolé",
        nature=ClaimNature.FAIT_ETABLI, support_level=SupportLevel.DOCUMENTE,
        proof_ids=[p3["proof_ref_id"]], decisive=True, derivation="source",
    )
    obj2 = await engine.graph.objective_etaye(inv2["id"], branch2["id"])
    assert obj2["etaye"] is False
    assert obj2["reponses_decisives"][0]["base"] == "insuffisant"
    inv3 = await make_investigation(engine, title="sans reponse decisive")
    branch3 = await first_branch(engine, inv3["id"])
    obj3 = await engine.graph.objective_etaye(inv3["id"], branch3["id"])
    assert obj3["etaye"] is False
    assert "aucune reponse decisive" in obj3["detail"][0]


async def test_confidence_is_multidimensional_and_qualitative(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    proof = await engine.filestore.store_proof(investigation_id=inv["id"], content=b"{}", source_url="https://example.test/1", connector_id="simulated.web")
    a = await engine.graph.add_assertion(
        inv["id"], branch_id=branch["id"], statement="x", proof_ids=[proof["proof_ref_id"]], decisive=True
    )
    conf = a["confidence"] if isinstance(a["confidence"], dict) else __import__("json").loads(a["confidence"])
    assert set(conf.keys()) == set(CONFIDENCE_DIMENSIONS)
    assert all(v in {"haute", "moyenne", "faible", "inconnue"} for v in conf.values())
    assert conf["fiabilite_source"] == "haute"
    etayage = await engine.graph.etayage(inv["id"])
    assert etayage[0]["support_level"] == "a_confirmer"
    assert etayage[0]["human_decision"] == "unexamined"
    assert etayage[0]["proofs"][0]["connector_id"] == "simulated.web"


async def test_correct_creates_superseding_assertion_and_keeps_original(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    a = await engine.graph.add_assertion(inv["id"], branch_id=branch["id"], statement="SIREN 1", decisive=True)
    dec = await engine.graph.decide(
        inv["id"], target_type="assertion", target_id=a["id"], action="correct",
        payload={"statement": "SIREN 2", "support_level": "documente"},
    )
    correction_id = dec["payload"]["correction_id"]
    orig = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    assert orig["superseded_by"] == correction_id
    active = await engine.graph.list_assertions(inv["id"])
    assert len(active) == 1 and active[0]["statement"] == "SIREN 2"
    everything = await engine.graph.list_assertions(inv["id"], include_superseded=True)
    assert len(everything) == 2
    events = await engine.repo.list_events(inv["id"])
    types = [e.type for e in events]
    assert "assertion.corrected" in types and "synthesis.stale" in types
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=dec["id"])
    orig = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    assert orig["superseded_by"] is None


async def test_api_graph_endpoints(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    a = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    b = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "ACME 2"}, identifiers={"siren": "987654321"})
    await engine.graph.add_relation(
        inv["id"], branch_id=branch["id"], src_id=a["entity_id"], dst_id=b["entity_id"], type="similaire",
        support_level=SupportLevel.A_CONFIRMER, derivation="ia",
    )
    registre = SimulatedConnector("simulated.registre")
    registre.manifest.primary_source = True
    engine.registry.register(registre)
    proof = await engine.filestore.store_proof(investigation_id=inv["id"], content=b"{}", source_url="https://registre.test/1", connector_id="simulated.registre")
    await engine.graph.add_assertion(
        inv["id"], branch_id=branch["id"], statement="ACME existe", nature=ClaimNature.FAIT_ETABLI,
        support_level=SupportLevel.DOCUMENTE, proof_ids=[proof["proof_ref_id"]], decisive=True, derivation="source",
    )
    async with await client_for(engine) as client:
        r = await client.get(f"/api/v1/investigations/{inv['id']}/graph")
        assert r.status_code == 200
        assert len(r.json()["entities"]) == 2 and len(r.json()["relations"]) == 1
        r = await client.get(f"/api/v1/investigations/{inv['id']}/graph", params={"branch_id": branch["id"]})
        assert len(r.json()["relations"]) == 1
        r = await client.get(f"/api/v1/investigations/{inv['id']}/entities/{a['entity_id']}")
        assert r.status_code == 200
        assert r.json()["identifiers"][0]["scheme"] == "siren"
        assert len(r.json()["relations_out"]) == 1
        r = await client.get(f"/api/v1/investigations/{inv['id']}/entities/inconnu")
        assert r.status_code == 404
        r = await client.post(
            f"/api/v1/investigations/{inv['id']}/matches",
            json={"entity_a": a["entity_id"], "entity_b": b["entity_id"], "basis": "similarity", "justification": "test"},
        )
        assert r.status_code == 201
        match_id = r.json()["id"]
        r = await client.get(f"/api/v1/investigations/{inv['id']}/matches")
        assert r.json()[0]["status"] == "proposed"
        r = await client.post(
            f"/api/v1/investigations/{inv['id']}/decisions",
            json={"target_type": "match_proposal", "target_id": match_id, "action": "validate"},
            headers={"actor": "testeur"},
        )
        assert r.status_code == 201
        assert r.json()["action"] == "validate"
        r = await client.get(f"/api/v1/investigations/{inv['id']}/decisions")
        assert any(d["action"] == "validate" for d in r.json())
        r = await client.get(f"/api/v1/investigations/{inv['id']}/assertions")
        assert r.json()[0]["nature"] == "fait_etabli"
        r = await client.get(f"/api/v1/investigations/{inv['id']}/etayage")
        assert set(r.json()[0]["confidence"].keys()) == set(CONFIDENCE_DIMENSIONS)
        r = await client.get(f"/api/v1/investigations/{inv['id']}/objectif", params={"branch_id": branch["id"]})
        assert r.status_code == 200
        assert r.json()["etaye"] is True
        r = await client.get(f"/api/v1/investigations/inconnu/graph")
        assert r.status_code == 404


async def test_undo_validate_restores_validation_dimension(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    a = await engine.graph.add_assertion(inv["id"], branch_id=branch["id"], statement="S", decisive=True)
    dec = await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="validate")
    row = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    conf = row["confidence"] if isinstance(row["confidence"], dict) else __import__("json").loads(row["confidence"])
    assert row["human_decision"] == "validated"
    assert conf["validation_humaine"] == "haute"
    with pytest.raises(PolicyDeny):
        await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="reject")
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=dec["id"])
    row = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    conf = row["confidence"] if isinstance(row["confidence"], dict) else __import__("json").loads(row["confidence"])
    assert row["human_decision"] == "unexamined"
    assert conf["validation_humaine"] == "inconnue"


async def test_undo_reject_match_restores_previous_support_levels(engine):
    inv = await make_investigation(engine)
    a = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "A"}, identifiers={"siren": "1"})
    b = await engine.graph.upsert_entity(inv["id"], kind="organisation", data={"name": "B"}, identifiers={"siren": "2"})
    prop = await engine.graph.propose_match(inv["id"], entity_a=a["entity_id"], entity_b=b["entity_id"], basis=MatchBasis.CROSS_REFERENCE)
    rel = await engine.graph.add_relation(
        inv["id"], branch_id=None, src_id=a["entity_id"], dst_id=b["entity_id"], type="capitalise",
        support_level=SupportLevel.CORROBORE, match_proposal_id=prop["id"], derivation="ia",
    )
    dec = await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="reject")
    row = await engine.pool.fetchrow("SELECT support_level FROM relations WHERE id = $1", rel["id"])
    assert row["support_level"] == "a_confirmer"
    await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="undo", reverts=dec["id"])
    row = await engine.pool.fetchrow("SELECT support_level FROM relations WHERE id = $1", rel["id"])
    assert row["support_level"] == "corrobore"


async def test_merge_and_decisions_rejected_on_already_decided_proposal(engine):
    inv = await make_investigation(engine)
    a = await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "X"}, identifiers={"passeport": "X1"})
    b = await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "Y"}, identifiers={"passeport": "Y1"})
    prop = await engine.graph.propose_match(inv["id"], entity_a=a["entity_id"], entity_b=b["entity_id"], basis=MatchBasis.SIMILARITY)
    dec = await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="reject")
    with pytest.raises(PolicyDeny):
        await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="merge")
    with pytest.raises(PolicyDeny):
        await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="validate")
    row = await engine.pool.fetchrow("SELECT merged_into FROM entities WHERE id = $1", b["entity_id"])
    assert row["merged_into"] is None
    await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="undo", reverts=dec["id"])
    merge = await engine.graph.decide(inv["id"], target_type="match_proposal", target_id=prop["id"], action="merge")
    row = await engine.pool.fetchrow("SELECT merged_into FROM entities WHERE id = $1", b["entity_id"])
    assert row["merged_into"] == a["entity_id"]


async def test_undo_blocked_when_later_decision_exists(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    a = await engine.graph.add_assertion(inv["id"], branch_id=branch["id"], statement="S", decisive=True)
    first = await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="reject")
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=first["id"])
    second = await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="validate")
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=second["id"])
    with pytest.raises(PolicyDeny):
        await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=first["id"])
    row = await engine.pool.fetchrow("SELECT human_decision FROM assertions WHERE id = $1", a["id"])
    assert row["human_decision"] == "unexamined"


async def test_undo_correct_deactivates_correction(engine):
    inv = await make_investigation(engine)
    branch = await first_branch(engine, inv["id"])
    a = await engine.graph.add_assertion(inv["id"], branch_id=branch["id"], statement="Original", decisive=True)
    dec = await engine.graph.decide(
        inv["id"], target_type="assertion", target_id=a["id"], action="correct",
        payload={"statement": "Corrige", "support_level": "documente"},
    )
    correction_id = dec["payload"]["correction_id"]
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=a["id"], action="undo", reverts=dec["id"])
    orig = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", a["id"])
    correction = await engine.pool.fetchrow("SELECT * FROM assertions WHERE id = $1", correction_id)
    assert orig["superseded_by"] is None
    assert correction["superseded_by"] == a["id"]
    active = await engine.graph.list_assertions(inv["id"])
    assert len(active) == 1 and active[0]["statement"] == "Original"
