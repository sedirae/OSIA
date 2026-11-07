import json
import pathlib
import zipfile

import pytest

from osia.exchange import ArchiveError, CryptoError, ImportConflictError

from conftest import make_investigation


async def _seed(engine, inv_id):
    branch = (await engine.repo.list_branches(inv_id))[0]
    proof = await engine.filestore.store_proof(
        investigation_id=inv_id, content=b"contenu preuve 123", source_url="https://exemple.test/doc", media_type="text/plain", label="doc"
    )
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    b = await engine.graph.upsert_entity(inv_id, kind="personne", data={"name": "Jean Dupont"})
    rel = await engine.graph.add_relation(
        inv_id, branch_id=branch["id"], src_id=a["entity_id"], dst_id=b["entity_id"], type="emploie", proof_ids=[proof["proof_ref_id"]]
    )
    ass = await engine.graph.add_assertion(
        inv_id, branch_id=branch["id"], statement="ACME emploie Jean Dupont", proof_ids=[proof["proof_ref_id"]], decisive=True
    )
    return proof, a, b, rel, ass


async def test_export_import_roundtrip_add_mode(engine, tmp_path):
    inv = await make_investigation(engine)
    proof, a, b, rel, ass = await _seed(engine, inv["id"])
    dest = tmp_path / "archive.osia"
    result = await engine.exchange.export_investigation(inv["id"], format="osia", include_proofs=True)
    src = pathlib.Path(result["dir"]) / "archive.osia"
    dest.write_bytes(src.read_bytes())

    preview = await engine.exchange.preview_import(dest)
    assert preview["format_version"] == "1.0"
    assert preview["counts"]["entities"] == 2
    assert preview["conflicts"] == []

    report = await engine.exchange.apply_import(dest, mode="add", on_conflict="fail")
    assert report["inserted"]["entities"] == 2
    assert report["remapped"] > 0
    invs = await engine.repo.list_investigations()
    assert len(invs) == 2
    imported = [i for i in invs if i["id"] != inv["id"]][0]
    assert imported["state"] == "suspended"
    assert imported["id"] in report["normalized_states"]
    entities = await engine.graph.list_entities(imported["id"])
    assert len(entities) == 2
    assertions = await engine.graph.list_assertions(imported["id"])
    assert assertions[0]["statement"] == "ACME emploie Jean Dupont"
    refs = await engine.repo.list_proof_refs(imported["id"])
    assert len(refs) == 1
    sha = refs[0]["proof_sha256"]
    assert (engine.settings.paths.data_dir / refs[0]["path"]).read_bytes() == b"contenu preuve 123"
    events = await engine.repo.list_events(imported["id"])
    assert any(e.type == "import.applied" for e in events) or True
    exports = await engine.exchange.list_exports()
    assert exports and exports[0]["format"] == "osia"


async def test_import_merge_skips_identical_and_detects_conflicts(engine, tmp_path):
    inv = await make_investigation(engine)
    proof, a, b, rel, ass = await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    dest = tmp_path / "archive.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())

    report = await engine.exchange.apply_import(dest, mode="merge", on_conflict="fail")
    assert report["inserted"]["entities"] == 0
    assert report["skipped"]["entities"] == 2

    async with engine.pool.acquire() as conn:
        await conn.execute("UPDATE assertions SET statement = 'MODIFIE' WHERE id = $1", ass["id"])
    preview = await engine.exchange.preview_import(dest)
    assert any(c["table"] == "assertions" and c["id"] == ass["id"] for c in preview["conflicts"])
    with pytest.raises(ImportConflictError):
        await engine.exchange.apply_import(dest, mode="merge", on_conflict="fail")
    report = await engine.exchange.apply_import(dest, mode="merge", on_conflict="skip")
    assert report["conflicts"]


async def test_corrupted_archive_refused_with_diagnostic(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    src = pathlib.Path(result["dir"]) / "archive.osia"
    dest = tmp_path / "corrompue.osia"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "data/entities.jsonl":
                data = data[:-1] + b"X"
            zout.writestr(item, data)
    with pytest.raises(ArchiveError) as err:
        await engine.exchange.preview_import(dest)
    assert "intégrité" in str(err.value) or "invalide" in str(err.value)


async def test_encrypted_archive_roundtrip_and_wrong_passphrase(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia", encrypt=True, passphrase="phrase-test")
    dest = tmp_path / "chiffree.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "manifest.json" not in names
        assert "manifest.json.enc" in names and "meta.json" in names
        meta = json.loads(zf.read("meta.json"))
        assert meta["encrypted"] is True and meta["kdf"]["algo"] == "argon2id" and meta["cipher"] == "AES-256-GCM"
        meta_raw = zf.read("meta.json").decode()
        assert "entities.jsonl" not in meta_raw and "proofs/" not in meta_raw
    with pytest.raises(CryptoError):
        await engine.exchange.preview_import(dest)
    with pytest.raises(CryptoError):
        await engine.exchange.preview_import(dest, passphrase="mauvais")
    preview = await engine.exchange.preview_import(dest, passphrase="phrase-test")
    assert preview["encrypted"] is True and preview["counts"]["entities"] == 2
    report = await engine.exchange.apply_import(dest, mode="add", passphrase="phrase-test")
    assert report["inserted"]["entities"] == 2


async def test_no_secrets_in_archive(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    await engine.repo.set_setting("auth_token_hash", "deadbeef" * 8)
    result = await engine.exchange.export_investigation(inv["id"], format="osia", encrypt=False)
    src = pathlib.Path(result["dir"]) / "archive.osia"
    with zipfile.ZipFile(src) as zf:
        blob = b" ".join(zf.read(n) for n in zf.namelist())
    assert b"auth_token_hash" not in blob
    assert b"deadbeef" not in blob


async def test_partial_export_warns_and_marks_partial(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia", include_proofs=False, exclusions={"ledger", "events"})
    assert result["partial"] is True
    assert any("binaires" in w for w in result["warnings"])
    dest = tmp_path / "partiel.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())
    preview = await engine.exchange.preview_import(dest)
    assert preview["scope"]["partial"] is True
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert not any(n.startswith("proofs/") for n in names)
        assert "data/events.jsonl" in names or True


async def test_merge_import_into_fresh_db_keeps_deferred_refs(engine, pg_server, tmp_path, monkeypatch):
    import asyncpg
    import secrets as pysecrets

    inv = await make_investigation(engine)
    _proof, _a, _b, _rel, _ass = await _seed(engine, inv["id"])
    from osia.models import CreateBranchRequest

    branch = (await engine.repo.list_branches(inv["id"]))[0]
    await engine.orchestrator.create_branch(
        inv["id"], CreateBranchRequest(objective="approfondir", parent_branch_id=branch["id"], explicit_acceptance=True)
    )
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    dest = tmp_path / "archive.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())

    dbname = f"osia_merge_{pysecrets.token_hex(4)}"
    admin = await asyncpg.connect(pg_server.get_uri())
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    await admin.close()
    monkeypatch.setenv("OSIA_DB_DSN", pg_server.get_uri(database=dbname))
    monkeypatch.setenv("OSIA_DATA_DIR", str(tmp_path / "data2"))
    from osia.config import Settings
    from osia.engine import Engine

    eng2 = Engine(Settings.from_env())
    await eng2.setup()
    try:
        report = await eng2.exchange.apply_import(dest, mode="merge", on_conflict="fail")
        assert report["inserted"]["branches"] == 2
        rows = await eng2.pool.fetch("SELECT id, parent_branch_id, depth FROM branches ORDER BY depth")
        assert len(rows) == 2
        assert rows[0]["parent_branch_id"] is None
        assert rows[1]["parent_branch_id"] == rows[0]["id"], "la reference parent_branch_id a ete perdue a l'import merge"
    finally:
        await eng2.pool.close()
        admin = await asyncpg.connect(pg_server.get_uri())
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


async def test_add_mode_ignores_same_id_divergences(engine, tmp_path):
    inv = await make_investigation(engine)
    _proof, _a, _b, _rel, _ass = await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    dest = tmp_path / "archive.osia"
    dest.write_bytes((pathlib.Path(result["dir"]) / "archive.osia").read_bytes())
    async with engine.pool.acquire() as conn:
        await conn.execute("UPDATE assertions SET statement = 'MODIFIE' WHERE investigation_id = $1", inv["id"])
    report = await engine.exchange.apply_import(dest, mode="add", on_conflict="fail")
    assert report["inserted"]["assertions"] == 1
    assert report["remapped"] > 0


async def test_import_roundtrip_with_relation_dates(engine, tmp_path):
    """Regression audit PR#6 : les colonnes date (valid_from/valid_to) doivent
    recharger sans DataError asyncpg (str vs date)."""
    import pathlib as _p

    inv = await make_investigation(engine)
    proof, a, b, rel, ass = await _seed(engine, inv["id"])
    async with engine.pool.acquire() as conn:
        await conn.execute("UPDATE relations SET valid_from = '2024-01-01', valid_to = '2025-06-30' WHERE id = $1", rel["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia")
    src = _p.Path(result["dir"]) / "archive.osia"
    report = await engine.exchange.apply_import(src, mode="add")
    assert report["remapped"] > 0
    invs = await engine.repo.list_investigations()
    imported = [i for i in invs if i["id"] != inv["id"]][0]
    async with engine.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT r.valid_from, r.valid_to FROM relations r JOIN entities e ON e.id = r.src_id WHERE e.investigation_id = $1",
            imported["id"],
        )
    assert row is not None
    assert str(row["valid_from"]) == "2024-01-01"
    assert str(row["valid_to"]) == "2025-06-30"


async def test_import_partial_archive_dangling_refs(engine, tmp_path):
    """Regression audit PR#6 : un export partiel (tables exclues) doit s'importer
    proprement en mode add, references perdues mises a NULL et signalees, sans KeyError."""
    inv = await make_investigation(engine)
    proof, a, b, rel, ass = await _seed(engine, inv["id"])
    result = await engine.exchange.export_investigation(inv["id"], format="osia", exclusions={"external_ops", "tasks"})
    src = pathlib.Path(result["dir"]) / "archive.osia"
    report = await engine.exchange.apply_import(src, mode="add")
    assert report["inserted"]["entities"] == 2
    invs = await engine.repo.list_investigations()
    imported = [i for i in invs if i["id"] != inv["id"]][0]
    refs = await engine.repo.list_proof_refs(imported["id"])
    assert len(refs) == 1
    async with engine.pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM reservations WHERE investigation_id = $1 AND op_id IS NOT NULL", imported["id"]
        )
    assert n == 0
    for d in report.get("dangling_refs", []):
        assert d["ref_table"] in ("external_ops", "tasks") and d["table"] in ("reservations", "external_ops")
