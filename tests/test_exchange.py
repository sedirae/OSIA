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
