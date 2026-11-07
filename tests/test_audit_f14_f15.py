"""Audit #17 — tranche 18 : F14 (sauvegarde/restauration) et F15 (SSE sans perte).

F14 : binaires PostgreSQL choisis selon la version majeure du serveur connecté (plus de
mélange pg_dump/pg_restore incompatible — cause de l'échec pg_restore en CI) ; exécution des
binaires en thread (la boucle d'événements n'est plus bloquée) avec stderr nettoyé des secrets
; dossier de sauvegarde unique (microseconde + suffixe, jamais de collision) ; inventaire de
configuration non secret dans le manifeste (secrets exclus, noms listés) ; restauration vers
une base externe avec `target_dsn` + `target_proofs_dir` EXPLICITE — les preuves courantes ne
sont jamais modifiées, et la sauvegarde préalable porte sur la base cible.

F15 : replay SSE paginé (aucun trou au-delà de 500 événements), header `Last-Event-ID` lu,
abonnement AVANT le replay (pas de fenêtre de perte), saturation de la file comptée
(`dropped`) avec resynchronisation explicite depuis la base.
"""

import asyncio
import json
import pathlib
import urllib.parse

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.backup.service import BackupError, _bin_major, _pg_bin, _scrub
from osia.events import SubscriberQueue

from conftest import make_investigation


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _seed(engine, inv_id):
    proof = await engine.filestore.store_proof(
        investigation_id=inv_id, content=b"preuve backup", source_url="https://exemple.test/p",
        media_type="text/plain", label="p",
    )
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": "ACME"}, identifiers={"siren": "123456789"})
    return proof, a


# ---------- F14 : sauvegarde / restauration ----------


def test_f14_pg_bin_prefers_server_major_match():
    """Le binaire choisi correspond à la version majeure du serveur (pas de mélange)."""
    embedded = _pg_bin("pg_dump", 16)
    assert _bin_major(embedded) == 16  # pgserver embarque du 16.x ici
    # version majeure inconnue -> repli déterministe (PATH s'il existe, sinon embarqué)
    fallback = _pg_bin("pg_dump", 99)
    assert pathlib.Path(fallback).exists()


def test_f14_scrub_removes_secrets():
    assert _scrub("connexion refusée password=hunter2 pour user", ["hunter2"]) == "connexion refusée password=*** pour user"


def test_f14_mask_dsn_hides_password():
    """P2-1 (audit PR #23) : le DSN journalisé dans l'événement backup.restored est masqué."""
    from osia.backup.service import _mask_dsn
    assert _mask_dsn("postgresql://user:hunter2@host:5432/db") == "postgresql://user:***@host:5432/db"
    assert _mask_dsn("postgresql://host/db") == "postgresql://host/db"
    assert _mask_dsn(None) is None


async def test_f14_backup_config_inventory_excludes_secrets(engine, tmp_path):
    """Le manifeste liste les fichiers de config inclus (empreintes) et les secrets exclus
    (noms seulement, jamais le contenu)."""
    cfg = engine.settings.paths.config_dir
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "osia.toml").write_text("[general]\nmode = \"desktop\"\n")
    (cfg / "auth_token").write_text("SECRET-ADMIN-TOKEN")
    (cfg / "secrets.key").write_bytes(b"SECRET-KEY-MATERIAL")
    result = await engine.backup.create(dest_dir=tmp_path / "bak")
    manifest = result["manifest"]
    assert any(f["path"] == "config/osia.toml" for f in manifest["config_files"])
    assert set(manifest["excluded_secret_files"]) == {"auth_token", "secrets.key"}
    dest = pathlib.Path(result["dest_dir"])
    blob = b"".join(p.read_bytes() for p in dest.rglob("*") if p.is_file())
    assert b"SECRET-ADMIN-TOKEN" not in blob
    assert b"SECRET-KEY-MATERIAL" not in blob
    # vérification d'intégrité couvre aussi les fichiers de config
    v = await engine.backup.verify(result["id"])
    assert v["verified"] is True


async def test_f14_backup_dirs_never_collide(engine, tmp_path):
    """Deux sauvegardes créées dans la même seconde ont des dossiers distincts."""
    r1 = await engine.backup.create()
    r2 = await engine.backup.create()
    assert r1["dest_dir"] != r2["dest_dir"]
    assert pathlib.Path(r1["dest_dir"]).is_dir() and pathlib.Path(r2["dest_dir"]).is_dir()


async def test_f14_restore_target_dsn_requires_explicit_proofs_dir(engine, tmp_path):
    """Restauration vers une base externe : target_proofs_dir EXPLICITE requis ; sans lui,
    refus explicite (les preuves courantes ne sont jamais modifiées)."""
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak")
    parsed = urllib.parse.urlparse(engine.settings.db_dsn)
    target_dsn = urllib.parse.urlunparse(parsed._replace(path="/osia_t18_target"))
    admin = await asyncpg.connect(urllib.parse.urlunparse(parsed._replace(path="/postgres")))
    await admin.execute('DROP DATABASE IF EXISTS "osia_t18_target"')
    await admin.execute('CREATE DATABASE "osia_t18_target"')
    await admin.close()
    try:
        with pytest.raises(BackupError, match="target-proofs-dir|target_proofs_dir|preuves"):
            await engine.backup.restore(result["id"], confirm=True, target_dsn=target_dsn)
        # avec dossier de preuves explicite : restauration OK, base cible peuplée, preuves courantes intactes
        proofs_before = sorted(p.name for p in (engine.settings.paths.proofs_dir / "sha256").rglob("*") if p.is_file())
        out = await engine.backup.restore(
            result["id"], confirm=True, target_dsn=target_dsn, target_proofs_dir=tmp_path / "target-proofs"
        )
        assert out["restored"] is True and out["target_proofs_dir"] == str(tmp_path / "target-proofs")
        conn = await asyncpg.connect(target_dsn)
        n = await conn.fetchval("SELECT COUNT(*) FROM investigations")
        await conn.close()
        assert n == 1
        assert (tmp_path / "target-proofs" / "sha256").is_dir()
        proofs_after = sorted(p.name for p in (engine.settings.paths.proofs_dir / "sha256").rglob("*") if p.is_file())
        assert proofs_before == proofs_after  # preuves courantes intactes
    finally:
        admin = await asyncpg.connect(urllib.parse.urlunparse(parsed._replace(path="/postgres")))
        await admin.execute('DROP DATABASE IF EXISTS "osia_t18_target" WITH (FORCE)')
        await admin.close()


async def test_f14_restore_in_place_keeps_pre_restore_backup(engine, tmp_path):
    """Restauration en place : sauvegarde préalable automatique si la base est non vide."""
    inv = await make_investigation(engine)
    proof, a = await _seed(engine, inv["id"])
    result = await engine.backup.create(dest_dir=tmp_path / "bak")
    await engine.graph.upsert_entity(inv["id"], kind="personne", data={"name": "Ajout après backup"})
    out = await engine.backup.restore(result["id"], confirm=True)
    assert out["restored"] is True and out["pre_restore_backup_id"]
    entities = await engine.graph.list_entities(inv["id"])
    assert len(entities) == 1
    backups = await engine.backup.list_backups()
    assert any(b["kind"] == "pre_restore" for b in backups)


# ---------- F15 : SSE sans perte silencieuse ----------


async def test_f15_json_replay_paginated_beyond_500(engine):
    """Le replay non-SSE est paginé : 600 événements en retard sont TOUS restitués."""
    inv = await make_investigation(engine)
    for i in range(600):
        await engine.bus.emit(type="test.burst", investigation_id=inv["id"], payload={"i": i})
    async with await client_for(engine) as client:
        r = await client.get(f"/api/v1/investigations/{inv['id']}/events")
        assert r.status_code == 200
        events = r.json()
        assert len(events) >= 600
        ids = [e["id"] for e in events]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)  # curseur monotone, sans trou


async def test_f15_last_event_id_header_and_param(engine):
    """Le header Last-Event-ID est lu (standard) et prime sur le paramètre de requête."""
    inv = await make_investigation(engine)
    for i in range(10):
        await engine.bus.emit(type="test.cursor", investigation_id=inv["id"], payload={"i": i})
    async with await client_for(engine) as client:
        all_events = (await client.get(f"/api/v1/investigations/{inv['id']}/events")).json()
        cut = all_events[4]["id"]
        r = await client.get(
            f"/api/v1/investigations/{inv['id']}/events",
            headers={"Last-Event-ID": str(cut)},
        )
        ids = [e["id"] for e in r.json()]
        assert ids and min(ids) > cut
        # le paramètre de requête fonctionne aussi
        r2 = await client.get(f"/api/v1/investigations/{inv['id']}/events?last_event_id={cut}")
        assert [e["id"] for e in r2.json()] == ids


async def test_f15_queue_saturation_is_counted_not_silent(engine):
    """Au-delà de la capacité de la file, la perte est COMPTÉE (dropped), jamais silencieuse."""
    inv = await make_investigation(engine)
    queue = engine.bus.subscribe(inv["id"])
    assert isinstance(queue, SubscriberQueue)
    for i in range(1001):
        await engine.bus.emit(type="test.flood", investigation_id=inv["id"], payload={"i": i})
    assert queue.dropped >= 1
    engine.bus.unsubscribe(queue)


async def test_f15_sse_stream_replays_then_live_without_gap(engine):
    """Flux SSE réel (uvicorn) : replay paginé puis événements live, ids contigus sans trou."""
    import uvicorn

    inv = await make_investigation(engine)
    for i in range(5):
        await engine.bus.emit(type="test.pre", investigation_id=inv["id"], payload={"i": i})
    app = create_app(engine)
    config = uvicorn.Config(app, host="127.0.0.1", port=18472, log_level="error")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    try:
        collected = ""

        async def emit_live():
            await asyncio.sleep(0.3)
            await engine.bus.emit(type="test.live", investigation_id=inv["id"], payload={"live": True})

        async with AsyncClient(base_url="http://127.0.0.1:18472", timeout=10) as client:
            task = asyncio.create_task(emit_live())
            async with client.stream(
                "GET", f"/api/v1/investigations/{inv['id']}/events",
                headers={"Accept": "text/event-stream", "Last-Event-ID": "0"},
            ) as r:
                assert r.status_code == 200
                async for chunk in r.aiter_text():
                    collected += chunk
                    if "event: test.live" in collected:
                        break
            await task
        ids = [int(line.split(":", 1)[1]) for line in collected.splitlines() if line.startswith("id: ")]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)  # curseur monotone, sans trou
        assert len(ids) >= 6  # 5 pre (replay paginé) + 1 live
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=10)
        except asyncio.TimeoutError:
            serve_task.cancel()
