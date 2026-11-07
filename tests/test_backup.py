import json
import pathlib

import pytest

from osia.backup import BackupError

from conftest import make_investigation


async def _seed(engine, inv_id):
    branch = (await engine.repo.list_branches(inv_id))[0]
    proof = await engine.filestore.store_proof(investigation_id=inv_id, content=b"preuve backup", source_url="https://exemple.test/p")
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    await engine.graph.add_assertion(inv_id, branch_id=branch["id"], statement="ACME existe", proof_ids=[proof["proof_ref_id"]])
    return proof, a


async def test_backup_create_and_verify(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak1")
    dest = pathlib.Path(result["dest_dir"])
    assert (dest / "manifest.json").exists()
    assert (dest / "db.dump").exists() or (dest / "db.sql").exists()
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["format"] == "osia-backup"
    assert manifest["counts"]["proof_files"] == 1
    assert any(p["path"].startswith("proofs/") for p in manifest["proof_files"])
    verification = await engine.backup.verify(result["id"])
    assert verification["verified"] is True
    assert verification["errors"] == []
    rows = await engine.backup.list_backups()
    assert rows[0]["id"] == result["id"] and rows[0]["verified_at"] is not None


async def test_backup_verify_detects_corruption(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak2")
    dest = pathlib.Path(result["dest_dir"])
    manifest = json.loads((dest / "manifest.json").read_text())
    target = dest / manifest["proof_files"][0]["path"]
    target.write_bytes(target.read_bytes() + b"X")
    verification = await engine.backup.verify(result["id"])
    assert verification["verified"] is False
    assert verification["errors"]


async def test_restore_requires_explicit_confirmation(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak3")
    with pytest.raises(BackupError):
        await engine.backup.restore(result["id"], confirm=False)


async def test_restore_roundtrip_with_pre_restore_backup(engine, tmp_path):
    inv = await make_investigation(engine)
    proof, a = await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak4")
    await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "Ajout après backup"})
    assert len(await engine.graph.list_entities(inv["id"])) == 2
    out = await engine.backup.restore(result["id"], confirm=True)
    assert out["restored"] is True
    assert out["pre_restore_backup_id"]
    entities = await engine.graph.list_entities(inv["id"])
    assert len(entities) == 1
    assert entities[0]["kind"] == "organisation"
    backups = await engine.backup.list_backups()
    assert any(b["kind"] == "pre_restore" for b in backups)
