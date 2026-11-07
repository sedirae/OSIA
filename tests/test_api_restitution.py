import json
import pathlib

from httpx import ASGITransport, AsyncClient

from osia.api import create_app

from conftest import make_investigation


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _seed(engine, inv_id):
    branch = (await engine.repo.list_branches(inv_id))[0]
    proof = await engine.filestore.store_proof(investigation_id=inv_id, content=b"preuve api", source_url="https://exemple.test/api")
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    await engine.graph.add_assertion(inv_id, branch_id=branch["id"], statement="ACME existe", proof_ids=[proof["proof_ref_id"]])
    return proof, a


async def test_api_export_both_download_preview_apply(engine):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    async with await client_for(engine) as client:
        r = await client.post(f"/api/v1/investigations/{inv['id']}/export", json={"format": "both"})
        assert r.status_code == 201
        body = r.json()
        assert {f["file"] for f in body["files"]} == {"archive.osia", "rapport.html"}
        export_id = body["export_id"]
        r = await client.get("/api/v1/exports")
        assert any(e["id"] == export_id for e in r.json())
        r = await client.get(f"/api/v1/exports/{export_id}/download?file=archive.osia")
        assert r.status_code == 200
        archive_bytes = r.content
        r = await client.get(f"/api/v1/exports/{export_id}/download?file=rapport.html")
        assert r.status_code == 200 and b"osia-data" in r.content
        r = await client.get(f"/api/v1/exports/{export_id}/download?file=inexistant.bin")
        assert r.status_code == 404
        r = await client.post("/api/v1/import/preview", content=archive_bytes, headers={"content-type": "application/octet-stream"})
        assert r.status_code == 200
        preview = r.json()
        assert preview["counts"]["entities"] == 1
        archive_path = pathlib.Path(engine.settings.paths.data_dir) / "exports" / export_id / "archive.osia"
        r = await client.post("/api/v1/import/apply", json={"path": str(archive_path), "mode": "add"})
        assert r.status_code == 201
        assert r.json()["inserted"]["entities"] == 1


async def test_api_export_encrypted_and_import_with_passphrase(engine):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    async with await client_for(engine) as client:
        r = await client.post(
            f"/api/v1/investigations/{inv['id']}/export",
            json={"format": "osia", "encrypt": True, "passphrase": "phrase-api"},
        )
        assert r.status_code == 201 and r.json()["encrypted"] is True
        export_id = r.json()["export_id"]
        archive_path = str(pathlib.Path(engine.settings.paths.data_dir) / "exports" / export_id / "archive.osia")
        r = await client.post("/api/v1/import/preview", json={"path": archive_path})
        assert r.status_code == 422 and r.json()["error"]["code"] == "crypto_error"
        r = await client.post("/api/v1/import/preview", json={"path": archive_path, "passphrase": "phrase-api"})
        assert r.status_code == 200


async def test_api_backups_create_verify(engine):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    async with await client_for(engine) as client:
        r = await client.post("/api/v1/backups", json={})
        assert r.status_code == 201
        backup_id = r.json()["id"]
        r = await client.get("/api/v1/backups")
        assert any(b["id"] == backup_id for b in r.json())
        r = await client.post(f"/api/v1/backups/{backup_id}/verify")
        assert r.status_code == 200 and r.json()["verified"] is True
        r = await client.get(f"/api/v1/backups/{backup_id}")
        assert r.json()["verified_at"] is not None
