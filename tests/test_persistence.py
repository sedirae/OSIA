import pytest

from osia.store import migrate

from conftest import make_investigation


async def test_migrate_is_idempotent(engine):
    applied = await migrate(engine.pool)
    assert applied == []


async def test_proof_store_dedup_and_integrity(engine):
    inv = await make_investigation(engine)
    p1 = await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"contenu preuve", source_url="https://ex.test/a", media_type="text/plain"
    )
    p2 = await engine.filestore.store_proof(
        investigation_id=inv["id"], content=b"contenu preuve", source_url="https://ex.test/b"
    )
    assert p1["sha256"] == p2["sha256"]
    assert p1["deduplicated"] is False
    assert p2["deduplicated"] is True
    refs = await engine.repo.list_proof_refs(inv["id"])
    assert len(refs) == 2
    files = await engine.repo.list_proof_files()
    assert len(files) == 1
    report = await engine.filestore.check_integrity()
    assert report.missing_files == []
    assert report.orphan_files == []
    assert engine.filestore.read_proof(p1["sha256"]) == b"contenu preuve"


async def test_crash_simulation_orphan_and_missing(engine):
    inv = await make_investigation(engine)
    part = engine.settings.paths.incoming_dir / "deadbeef.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"orphelin")
    import os
    import time

    stale = time.time() - 120
    os.utime(part, (stale, stale))
    fake_sha = "ab" * 32
    await engine.pool.execute(
        "INSERT INTO proof_files (sha256, path, size_bytes) VALUES ($1, $2, 3)",
        fake_sha,
        f"proofs/sha256/ab/ab/{fake_sha}",
    )
    report = await engine.filestore.check_integrity()
    assert str(part) in report.orphan_files
    assert fake_sha in report.missing_files
    removed = await engine.filestore.purge_orphans(report)
    assert removed == 1
    assert not part.exists()
    still = await engine.repo.list_proof_files()
    assert len(still) == 1
