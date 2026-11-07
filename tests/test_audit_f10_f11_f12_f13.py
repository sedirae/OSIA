"""Audit #17 — tranche 17 : F10 (références d'import), F11 (connexion web serveur),
F12 (périmètre des exports sélectifs), F13 (originaux HTTP/PDF + qualification connecteurs).

F10 : en mode "add", TOUTES les références sont remappées — colonnes FK (dont
`external_ops.reservation_id`), tableaux JSON (`proof_ids`, `contradicted_by`) et objets
JSON profonds (payloads de décisions/tâches/événements, `external_ops.result`) — puis une
vérification d'intégrité référentielle métier est exécutée après import (report["integrity"]).
Règle explicite : une réservation importée non résolue ('reserved') est importée 'released'
pour ne pas peser sur les plafonds financiers locaux.

F11 : le shell web ('/' et '/static/*') est servi sans authentification en mode serveur (il ne
contient aucune donnée sensible) ; l'API reste protégée. Le frontend échange le jeton admin
contre une session `sess_*` expirable/révocable (tests dans test_web.py).

F12 : un export restreint à des branches exporte la FERMETURE du périmètre : décisions et
preuves (proof_refs/proof_files) filtrées, et le rapport HTML calcule étayage/objectif sur le
même périmètre (plus de marqueur d'une autre branche dans le JSON embarqué).

F13 : `FetchResult.raw_bytes` conserve les octets originaux (la preuve stocke ces octets, pas
le texte normalisé) ; un statut HTTP >= 400 lève HttpStatusError (distinct d'un résultat vide) ;
le handler appelle `validate_response` avant stockage/cache/exploitation et refuse une réponse
de structure invalide.
"""

import hashlib
import json
import pathlib
import zipfile

import pytest

from osia.connectors.base import ConnectorManifest, FetchRequest, FetchResult, TrustLevel
from osia.connectors.http import HttpConnector, HttpStatusError
from osia.connectors.real import WebUrlConnector
from osia.models import CreateBranchRequest
from osia.tasks import TaskContext, handle_source_query

from conftest import make_investigation


async def _branch(engine, inv):
    return (await engine.repo.list_branches(inv["id"]))[0]


async def _insert(engine, inv, branch_id, kind, payload, depth=0, priority=10):
    return await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branch_id, kind=kind, payload=payload, depth=depth, priority=priority
    )


async def _seed_rich(engine, inv_id):
    """Investigation avec preuve, relation, deux assertions (contradiction), une décision
    avec payload embarqué, et une opération externe réservée (réservation)."""
    branch = (await engine.repo.list_branches(inv_id))[0]
    proof = await engine.filestore.store_proof(
        investigation_id=inv_id, content=b"contenu preuve original", source_url="https://exemple.test/doc",
        media_type="text/plain", label="doc",
    )
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    b = await engine.graph.upsert_entity(inv_id, kind="personne", data={"name": "Jean Dupont"})
    rel = await engine.graph.add_relation(
        inv_id, branch_id=branch["id"], src_id=a["entity_id"], dst_id=b["entity_id"], type="emploie",
        proof_ids=[proof["proof_ref_id"]],
    )
    ass1 = await engine.graph.add_assertion(
        inv_id, branch_id=branch["id"], statement="ACME emploie Jean Dupont", proof_ids=[proof["proof_ref_id"]], decisive=True,
    )
    ass2 = await engine.graph.add_assertion(
        inv_id, branch_id=branch["id"], statement="ACME n'emploie pas Jean Dupont", contradicted_by=[ass1["id"]],
    )
    decision = await engine.graph.decide(
        inv_id, target_type="assertion", target_id=ass1["id"], action="reject",
        payload={"assertion_id": ass1["id"], "note": "rejet humain"},
    )
    # opération externe avec réservation (chemin test_budgets : insert_op + reserve)
    await engine.repo.set_setting("paid_calls_enabled", True)
    op = await engine.repo.insert_op(investigation_id=inv_id, kind="source_request", target="simulated.web", is_paid=True, cost_estimated_cents=1)
    res = await engine.budgets.reserve(
        idempotency_key=f"{op['id']}:reserve", investigation_id=inv_id, branch_id=branch["id"], op_id=op["id"], amount_cents=1,
    )
    await engine.pool.execute(
        "UPDATE external_ops SET state = 'reserved', reservation_id = $2, updated_at = now() WHERE id = $1",
        op["id"], res["id"],
    )
    return proof, rel, ass1, ass2, decision, res


# ---------- F10 : références d'import ----------


async def test_f10_import_add_remappe_toutes_les_references(engine, tmp_path):
    """Mode add : proof_ids, contradicted_by, payload de décision (objet profond),
    target_id de décision et external_ops.reservation_id sont remappés vers les nouveaux
    identifiants, et l'intégrité référentielle est vérifiée après import."""
    inv = await make_investigation(engine)
    proof, rel, ass1, ass2, decision, res = await _seed_rich(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia", include_proofs=True)
    dest = tmp_path / "archive.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())

    report = await engine.exchange.apply_import(dest, mode="add", on_conflict="fail")
    assert report["integrity"] == "ok", report.get("dangling_refs")
    assert not report.get("dangling_refs")
    assert not report.get("ambiguous_refs")

    imported = [i for i in await engine.repo.list_investigations() if i["id"] != inv["id"]][0]
    iid = imported["id"]

    # proof_refs remappés : l'assertion importée pointe vers le NOUVEL id de preuve
    refs = await engine.repo.list_proof_refs(iid)
    assert len(refs) == 1
    new_proof_id = refs[0]["id"]
    assert new_proof_id != proof["proof_ref_id"]
    assertions = {a["statement"]: a for a in await engine.graph.list_assertions(iid, include_superseded=True)}
    a1 = assertions["ACME emploie Jean Dupont"]
    a2 = assertions["ACME n'emploie pas Jean Dupont"]
    assert a1["proof_ids"] == [new_proof_id]
    cb = a2["contradicted_by"]
    cb = json.loads(cb) if isinstance(cb, str) else cb
    assert cb == [a1["id"]]  # remappé, pas l'ancien id
    assert cb[0] != ass1["id"]

    async with engine.pool.acquire() as conn:
        # relations : proof_ids remappé
        rels = await conn.fetch("SELECT proof_ids FROM relations WHERE investigation_id = $1", iid)
        assert json.loads(rels[0]["proof_ids"]) == [new_proof_id]
        # décision : assertion_id + target_id remappés, payload profond remappé
        dec = await conn.fetchrow("SELECT * FROM decisions WHERE investigation_id = $1", iid)
        assert dec["assertion_id"] == a1["id"]
        assert dec["target_id"] == a1["id"]
        payload = json.loads(dec["payload"]) if isinstance(dec["payload"], str) else dec["payload"]
        assert payload["assertion_id"] == a1["id"]
        assert payload["note"] == "rejet humain"
        # external_ops.reservation_id remappé vers la nouvelle réservation
        ops = await conn.fetch("SELECT id, reservation_id FROM external_ops WHERE investigation_id = $1", iid)
        assert len(ops) == 1 and ops[0]["reservation_id"] is not None
        assert ops[0]["reservation_id"] != res["id"]
        res = await conn.fetch("SELECT id, state FROM reservations WHERE investigation_id = $1", iid)
        assert len(res) == 1
        assert res[0]["id"] == ops[0]["reservation_id"]
        # règle explicite F10 : réservation importée non résolue -> 'released' (pas de poids local)
        assert res[0]["state"] == "released"
        assert report["released_reservations"]
        # la preuve importée conserve les octets d'origine
        pf = await conn.fetchrow(
            "SELECT pf.path FROM proof_files pf JOIN proof_refs pr ON pr.proof_sha256 = pf.sha256 WHERE pr.investigation_id = $1", iid
        )
    assert (engine.settings.paths.data_dir / pf["path"]).read_bytes() == b"contenu preuve original"


async def test_f10_import_merge_conserve_ids_et_verifie_integrite(engine, tmp_path):
    """Mode merge : ids conservés (pas de remap), lignes identiques ignorées, intégrité ok."""
    inv = await make_investigation(engine)
    await _seed_rich(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    dest = tmp_path / "archive.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())
    report = await engine.exchange.apply_import(dest, mode="merge", on_conflict="skip")
    assert report["integrity"] == "ok"
    assert report["inserted"]["assertions"] == 0  # déjà présents -> ignorés
    assertions = await engine.graph.list_assertions(inv["id"], include_superseded=True)
    a1 = [a for a in assertions if a["statement"] == "ACME emploie Jean Dupont"][0]
    assert a1["proof_ids"]  # ids conservés tels quels


# ---------- F12 : périmètre des exports sélectifs ----------


async def test_f12_export_branche_fermeture_complete(engine, tmp_path):
    """Export restreint à la branche racine : aucune donnée de la branche B (assertion
    marqueur, décision, preuve) dans le payload NI dans le rapport HTML embarqué."""
    inv = await make_investigation(engine)
    root = await _branch(engine, inv)
    branch_b = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="branche B", parent_branch_id=root["id"], explicit_acceptance=True)
    )
    proof_root = await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"preuve racine", source_url="https://exemple.test/root",
        media_type="text/plain", label="root",
    )
    proof_b = await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"preuve branche B SECRETE", source_url="https://exemple.test/b",
        media_type="text/plain", label="b",
    )
    await engine.graph.add_assertion(
        inv["id"], branch_id=root["id"], statement="assertion racine", proof_ids=[proof_root["proof_ref_id"]], decisive=True,
    )
    ass_b = await engine.graph.add_assertion(
        inv["id"], branch_id=branch_b["id"], statement="MARQUEUR-B-secret", proof_ids=[proof_b["proof_ref_id"]],
    )
    await engine.graph.decide(inv["id"], target_type="assertion", target_id=ass_b["id"], action="reject")

    def read_tables(archive_path):
        tables = {}
        with zipfile.ZipFile(archive_path) as zf:
            for name in zf.namelist():
                if name.startswith("data/") and name.endswith(".jsonl"):
                    body = zf.read(name).decode("utf-8").strip()
                    tables[name[len("data/"):-len(".jsonl")]] = [json.loads(l) for l in body.splitlines() if l]
        return tables

    result = await engine.exchange.export_investigation(inv["id"], format="both", branch_ids=[root["id"]], include_proofs=True)
    out = pathlib.Path(result["dir"])
    payload = read_tables(out / "archive.osia")
    assert all("MARQUEUR-B" not in json.dumps(r) for rows in payload.values() for r in rows)
    assert [r["id"] for r in payload["proof_refs"]] == [proof_root["proof_ref_id"]]
    assert all("MARQUEUR-B" not in r["statement"] for r in payload["assertions"])
    # la décision sur l'assertion de B n'est pas exportée
    assert all(d["target_id"] != ass_b["id"] for d in payload["decisions"])
    # le rapport HTML embarqué ne contient pas le marqueur de B (étayage filtré aussi)
    html = (out / "rapport.html").read_text(encoding="utf-8")
    assert "MARQUEUR-B" not in html
    assert "preuve branche B SECRETE" not in html
    # sanity : l'export complet contient bien le marqueur
    result_all = await engine.exchange.export_investigation(inv["id"], format="osia")
    payload_all = read_tables(pathlib.Path(result_all["dir"]) / "archive.osia")
    assert any("MARQUEUR-B" in r["statement"] for r in payload_all["assertions"])


async def test_f12_etayage_et_objectif_filtres_par_branches(engine):
    """graph.etayage / objective_etaye acceptent branch_ids : les assertions de la branche B
    n'y figurent pas."""
    inv = await make_investigation(engine)
    root = await _branch(engine, inv)
    branch_b = await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="branche B", parent_branch_id=root["id"], explicit_acceptance=True)
    )
    await engine.graph.add_assertion(inv["id"], branch_id=root["id"], statement="assertion racine", decisive=True)
    await engine.graph.add_assertion(inv["id"], branch_id=branch_b["id"], statement="MARQUEUR-B-secret")
    etayage = await engine.graph.etayage(inv["id"], branch_ids=[root["id"]])
    assert all("MARQUEUR-B" not in e["statement"] for e in etayage)
    assert any(e["statement"] == "assertion racine" for e in etayage)
    obj = await engine.graph.objective_etaye(inv["id"], branch_ids=[root["id"]])
    assert all("MARQUEUR-B" not in json.dumps(r) for r in obj.get("reponses", []))


# ---------- F13 : originaux, statuts HTTP, validation sémantique ----------


HTML_BYTES = b"<html><body><h1>Page</h1><a href='https://exemple.test/lien'>lien</a></body></html>"


class _RawTestConnector(HttpConnector):
    """Connecteur de test concret : fetch = _get + résultat normalisé, octets originaux conservés."""

    async def fetch(self, request: FetchRequest) -> FetchResult:
        status, headers, body = await self._get(request.query)
        media = headers.get("content-type", "application/octet-stream").split(";")[0].strip().lower()
        text = body.decode("utf-8", errors="replace")
        return self._result(
            query=request.query, url=request.query, status=status,
            payload={"url": request.query, "media_type": media, "text": text},
            media_type=media, extracted_text=text, raw=body,
        )


def _raw_connector(cid, fetch_fn, validate=None):
    manifest = ConnectorManifest(id=cid, version="0.1.0", trust_level=TrustLevel.EXPERIMENTAL, capabilities=["web_fetch"], domains=["exemple.test"])
    conn = _RawTestConnector(manifest, fetch_fn=fetch_fn)
    if validate is not None:
        conn.validate_response = validate  # type: ignore[method-assign]
    return conn


async def test_f13_weburl_conserve_les_octets_originaux(monkeypatch):
    """web.url : raw_bytes = octets reçus tels quels (HTML), content = extraction dérivée."""
    async def fetch(url):
        return 200, {"content-type": "text/html; charset=utf-8"}, HTML_BYTES
    c = WebUrlConnector(fetch_fn=fetch)
    res = await c.fetch(FetchRequest(query="https://exemple.test/page"))
    assert res.raw_bytes == HTML_BYTES
    assert res.media_type == "text/html"
    assert "lien" in (res.extracted_text or "")
    assert res.content != HTML_BYTES.decode("utf-8")  # content normalisé, distinct de l'original

    # PDF : raw_bytes = binaire PDF d'origine, content = JSON de l'extraction
    async def fake_pdf_extract(data):
        return "TEXTE EXTRAIT DU PDF"
    monkeypatch.setattr("osia.connectors.real.extract_text_from_pdf_isolated", fake_pdf_extract)
    pdf_bytes = b"%PDF-1.4 fake binaire original"
    async def fetch_pdf(url):
        return 200, {"content-type": "application/pdf"}, pdf_bytes
    c2 = WebUrlConnector(fetch_fn=fetch_pdf)
    res2 = await c2.fetch(FetchRequest(query="https://exemple.test/doc.pdf"))
    assert res2.raw_bytes == pdf_bytes
    assert res2.media_type == "application/pdf"
    assert res2.extracted_text == "TEXTE EXTRAIT DU PDF"
    assert json.loads(res2.content)["text"] == "TEXTE EXTRAIT DU PDF"


async def test_f13_statut_http_400_plus_leve_une_erreur_distincte():
    """404/429/500 -> HttpStatusError (jamais un FetchResult « vide »)."""
    for status in (404, 429, 500):
        async def fetch(url, status=status):
            return status, {"content-type": "text/html"}, b"erreur"
        c = _raw_connector(f"test.http{status}", fetch)
        with pytest.raises(HttpStatusError) as exc:
            await c._get("https://exemple.test/x")
        assert exc.value.status == status


async def test_f13_handler_stocke_les_octets_originaux_et_cache(engine):
    """handle_source_query stocke la preuve sur raw_bytes (empreinte = octets reçus) et le
    cache conserve l'original (raw_b64) : un hit cache restaure les mêmes octets."""
    calls = []

    async def fetch(url):
        calls.append(url)
        return 200, {"content-type": "application/pdf"}, b"%PDF-1.4 binaire original"

    conn = _raw_connector("test.raw", fetch)
    engine.registry.register(conn, enabled=True)
    engine.policy.allow_target("test.raw")
    await engine.repo.set_setting("allow_experimental:test.raw", True)  # T5.1
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    ctx = TaskContext(engine=engine)
    task = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "test.raw", "query": "https://exemple.test/q1"})
    out = await handle_source_query(task, ctx)
    assert out["proof_sha256"] == hashlib.sha256(b"%PDF-1.4 binaire original").hexdigest()
    refs = await engine.repo.list_proof_refs(inv["id"])
    assert len(refs) == 1
    assert refs[0]["media_type"] == "application/pdf"
    async with engine.pool.acquire() as c:
        pf = await c.fetchrow("SELECT path FROM proof_files WHERE sha256 = $1", out["proof_sha256"])
    assert (engine.settings.paths.data_dir / pf["path"]).read_bytes() == b"%PDF-1.4 binaire original"

    # hit cache : même requête -> même traitement métier, octets originaux restaurés, 1 seul appel externe
    task2 = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "test.raw", "query": "https://exemple.test/q1"})
    out2 = await handle_source_query(task2, ctx)
    assert out2["cached"] is True
    assert len(calls) == 1
    assert out2["proof_sha256"] == out["proof_sha256"]
    refs2 = await engine.repo.list_proof_refs(inv["id"])
    assert len(refs2) == 2  # une preuve par exécution (même contenu, nouvelle preuve rattachée)


async def test_f13_handler_refuse_reponse_invalide_et_http_erreur(engine):
    """validate_response appelé avant stockage : réponse 200 de structure invalide -> refus
    explicite (pas de preuve, pas de cache) ; HTTP 404 -> erreur distincte, op incertaine."""
    inv = await make_investigation(engine)
    branch = await _branch(engine, inv)
    ctx = TaskContext(engine=engine)

    # réponse 200 mais structure invalide
    async def fetch_bad(url):
        return 200, {"content-type": "application/json"}, json.dumps({"pas_le_bon_schema": True}).encode()
    bad = _raw_connector("test.bad", fetch_bad, validate=lambda payload: ["champ 'results' absent"])
    engine.registry.register(bad, enabled=True)
    engine.policy.allow_target("test.bad")
    await engine.repo.set_setting("allow_experimental:test.bad", True)
    task = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "test.bad", "query": "https://exemple.test/q-bad"})
    with pytest.raises(RuntimeError, match="reponse_invalide"):
        await handle_source_query(task, ctx)
    assert await engine.repo.list_proof_refs(inv["id"]) == []
    assert await engine.repo.cache_get("test.bad", "https://exemple.test/q-bad") is None

    # HTTP 404 : erreur distincte d'un résultat vide, aucune preuve stockée
    async def fetch_404(url):
        return 404, {"content-type": "text/html"}, b"not found"
    c404 = _raw_connector("test.404", fetch_404)
    engine.registry.register(c404, enabled=True)
    engine.policy.allow_target("test.404")
    await engine.repo.set_setting("allow_experimental:test.404", True)
    task2 = await _insert(engine, inv, branch["id"], "source_query", {"connector_id": "test.404", "query": "https://exemple.test/q-404"})
    with pytest.raises(RuntimeError, match="http_status:404"):
        await handle_source_query(task2, ctx)
    assert await engine.repo.list_proof_refs(inv["id"]) == []
    async with engine.pool.acquire() as c:
        op = await c.fetchrow("SELECT state FROM external_ops WHERE target = 'test.404'")
        assert op["state"] == "uncertain"  # marqué incertain, pas « vide »
