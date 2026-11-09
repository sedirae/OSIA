"""CON-18 (C6, D4, T3.13, T5.9) : journaux et rétentions — trois finalités DISTINCTES :
audit de sécurité (T5.9), journal technique structuré (T3.13), historique métier en base
(events/decisions/external_ops/ledger — jamais purgé, D4 §6.1.A/§6.5).

Vérifications : entrées structurées avec corrélation + durées ; secrets masqués (même _scrub
que l'audit) ; permissions 0600 ; purges supervisées avec prévisualisation dry-run ; purge du
cache expiré (D4 §6.1.B) ; l'historique métier est conservé après toutes les purges ;
tech_log_retention_days exposé comme paramètre (D7 §9.1)."""

import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.techlog import TechLog
from osia.security.audit import SecurityAudit

from conftest import make_investigation

OLD_TS = "2020-01-01T00:00:00Z"  # hors rétention quelle que soit la rétention >= 1 jour


def _write_line(path, entry: dict) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------- Journal technique (T3.13) ----------


def test_techlog_structure_correlation_et_masquage_secrets(tmp_path):
    """Entrée structurée : ts/level/component/event + ids de corrélation + durée, et toute clé
    sensible (token, api_key, ...) est masquée — même règle que l'audit (T5.9/T3.13)."""
    log = TechLog(tmp_path / "logs", retention_days=30)
    log.log(
        "tasks", "source.query",
        investigation_id="inv_1", branch_id="br_1", task_id="task_1", op_id="op_1",
        duration_ms=42,
        detail={"connector_id": "simulated.web", "token": "secret-value", "api_key": "k123", "http_status": 200},
    )
    entries = log.read()
    assert len(entries) == 1
    e = entries[0]
    assert e["component"] == "tasks" and e["event"] == "source.query"
    assert e["investigation_id"] == "inv_1" and e["branch_id"] == "br_1"
    assert e["task_id"] == "task_1" and e["op_id"] == "op_1" and e["duration_ms"] == 42
    assert e["detail"]["connector_id"] == "simulated.web"
    assert e["detail"]["token"] == "***" and e["detail"]["api_key"] == "***"
    assert e["detail"]["http_status"] == 200
    raw = log.path.read_text(encoding="utf-8")
    assert "secret-value" not in raw and "k123" not in raw


def test_techlog_error_masque_et_fichier_0600(tmp_path):
    log = TechLog(tmp_path / "logs")
    log.log("ai.broker", "ai.call", level="error", error="échec token=abcdef", detail={"password": "x"})
    e = log.read()[0]
    assert e["level"] == "error"
    assert "abcdef" not in json.dumps(e)
    assert e["detail"]["password"] == "***"
    mode = stat.S_IMODE(os.stat(log.path).st_mode)
    assert mode == 0o600


def test_techlog_log_ne_leve_jamais(tmp_path):
    """T3.13 : un échec de journalisation (répertoire indisponible) ne fait jamais
    échouer l'opération métier qui déclenche l'écriture."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    log = TechLog(blocker, retention_days=30)
    log.log("tasks", "source.query", investigation_id="inv", detail={"token": "s"})  # ne lève pas
    assert log.read() == []


def test_techlog_purge_et_dry_run(tmp_path):
    """expired_count ne supprime rien (dry-run) ; purge supprime les entrées hors rétention."""
    log = TechLog(tmp_path / "logs", retention_days=30)
    log.log("engine", "engine.setup")
    _write_line(log.path, {"ts": OLD_TS, "level": "info", "component": "old", "event": "old.event"})
    _write_line(log.path, {"ts": OLD_TS, "level": "info", "component": "old", "event": "old.event2"})
    assert log.expired_count() == 2
    # dry-run : rien n'est supprimé
    assert log.expired_count() == 2
    remaining_before = len(log.read(limit=100))
    assert remaining_before == 3
    removed = log.purge()
    assert removed == 2  # deux entrées hors rétention supprimées (le fichier du jour est réécrit)
    entries = log.read()
    assert len(entries) == 1 and entries[0]["event"] == "engine.setup"
    assert log.expired_count() == 0


# ---------- Audit de sécurité : purge supervisée (C6/D4) ----------


def test_audit_purge_et_dry_run(tmp_path):
    audit = SecurityAudit(tmp_path / "logs", retention_days=90)
    audit.log("op.test", "success", detail={"k": "v"})
    _write_line(audit.path, {"ts": OLD_TS, "action": "old", "outcome": "success", "client": None, "detail": {}})
    assert audit.expired_count() == 1
    assert len(audit.read()) == 2  # dry-run : rien de supprimé
    removed = audit.purge()
    assert removed == 1
    entries = audit.read()
    assert len(entries) == 1 and entries[0]["action"] == "op.test"
    assert audit.purge() == 0  # plus rien à purger


# ---------- API : les trois finalités + purges supervisées ----------


async def test_api_logs_overview_trois_finalites(engine):
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        r = await client.get("/api/v1/logs")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"audit_security", "tech_log", "business_history"}
        assert body["audit_security"]["retention_days"] == engine.audit.retention_days
        assert body["tech_log"]["retention_days"] == engine.techlog.retention_days
        # D4 §6.1.A : l'historique métier n'a JAMAIS de rétention automatique
        assert body["business_history"]["retention_days"] is None
        assert "jamais" in body["business_history"]["note"].lower() or "D4" in body["business_history"]["note"]


async def test_api_logs_purge_dry_run_puis_reel_et_audite(engine):
    # NB : l'audit purge à chaque écrit (rétention D4) — on injecte donc l'entrée expirée
    # juste avant chaque appel pour que la prévisualisation la voie.
    _write_line(engine.techlog.path, {"ts": OLD_TS, "level": "info", "component": "old", "event": "old"})
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # dry-run tech : prévisualisation sans suppression
        r = await client.post("/api/v1/logs/purge", json={"kind": "tech", "dry_run": True})
        assert r.status_code == 200
        assert r.json()["expired_entries"] == 1
        assert engine.techlog.expired_count() == 1  # rien supprimé
        # purge réelle tech
        r = await client.post("/api/v1/logs/purge", json={"kind": "tech", "dry_run": False})
        assert r.json()["removed_entries"] == 1
        assert engine.techlog.expired_count() == 0
        # dry-run audit (l'entrée expirée est injectée juste avant l'appel)
        _write_line(engine.audit.path, {"ts": OLD_TS, "action": "old", "outcome": "success", "client": None, "detail": {}})
        r = await client.post("/api/v1/logs/purge", json={"kind": "audit", "dry_run": True})
        assert r.json()["expired_entries"] == 1
        # purge réelle audit (réinjection car l'audit purge à chaque écrit)
        _write_line(engine.audit.path, {"ts": OLD_TS, "action": "old", "outcome": "success", "client": None, "detail": {}})
        r = await client.post("/api/v1/logs/purge", json={"kind": "audit", "dry_run": False})
        assert r.json()["removed_entries"] == 1
        # les purges elles-mêmes sont auditées (T5.9)
        actions = [e["action"] for e in engine.audit.read(limit=50)]
        assert actions.count("op.logs.purge") == 4


async def test_api_cache_purge_dry_run_puis_reel(engine):
    # deux entrées de cache, une expirée
    await engine.repo.cache_set("simulated.web", "requete fraiche", {"content": "x"}, ttl_hours=24)
    await engine.pool.execute(
        "INSERT INTO source_cache (id, connector_id, query_hash, result, fetched_at, expires_at) "
        "VALUES ($1, $2, $3, $4::jsonb, now() - interval '2 hours', now() - interval '1 hour')",
        "cache_old1", "simulated.web", engine.repo.cache_key("simulated.web", "requete expiree"),
        json.dumps({"content": "y"}),
    )
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        r = await client.post("/api/v1/cache/purge", json={"dry_run": True})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True and body["expired_entries"] == 1 and body["expired_bytes"] > 0
        # dry-run : l'entrée expirée est toujours là
        assert (await engine.repo.cache_expired_stats())["entries"] == 1
        r = await client.post("/api/v1/cache/purge", json={"dry_run": False})
        assert r.json()["purged_entries"] == 1
        assert (await engine.repo.cache_expired_stats())["entries"] == 0
        # l'entrée valide est conservée
        cached = await engine.repo.cache_get("simulated.web", "requete fraiche")
        assert cached is not None and cached["content"] == "x"
        actions = [e["action"] for e in engine.audit.read(limit=50)]
        assert actions.count("op.cache.purge") == 2


async def test_historique_metier_conserve_apres_purges(engine):
    """D4 §6.5 (règle intangible) : purger tech/audit/cache ne touche JAMAIS à l'historique
    métier (table events) — conservé tant que l'investigation est conservée."""
    inv = await make_investigation(engine, objective="objectif test")
    branches = await engine.repo.list_branches(inv["id"])
    await engine.bus.emit(type="test.event", investigation_id=inv["id"], branch_id=branches[0]["id"], payload={"note": "métier"})
    events_before = await engine.repo.list_events(inv["id"])
    assert len(events_before) >= 1
    _write_line(engine.audit.path, {"ts": OLD_TS, "action": "old", "outcome": "success", "client": None, "detail": {}})
    _write_line(engine.techlog.path, {"ts": OLD_TS, "level": "info", "component": "old", "event": "old"})
    await engine.repo.cache_set("simulated.web", "q", {"content": "z"}, ttl_hours=24)
    await engine.pool.execute(
        "UPDATE source_cache SET expires_at = now() - interval '1 hour' WHERE connector_id = 'simulated.web'"
    )
    engine.audit.purge()
    engine.techlog.purge()
    await engine.repo.cache_purge_expired()
    events_after = await engine.repo.list_events(inv["id"])
    assert [e.id for e in events_after] == [e.id for e in events_before]
    assert any(e.type == "test.event" for e in events_after)
    # le cache purgé ne contient plus rien, mais l'investigation et ses événements sont intacts
    assert (await engine.repo.cache_expired_stats())["entries"] == 0
    assert (await engine.repo.get_investigation(inv["id"]))["id"] == inv["id"]


async def test_tech_log_retention_days_parametre_visible_et_modifiable(engine):
    """D7 §9.1 : tech_log_retention_days est un paramètre global éditable, borné (>= 1)."""
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        r = await client.get("/api/v1/settings")
        assert r.json()["settings"]["tech_log_retention_days"] == 30
        r = await client.put("/api/v1/settings", json={"settings": {"tech_log_retention_days": 7}})
        assert r.status_code == 200
        assert engine.techlog.retention_days == 7  # appliqué à chaud
        r = await client.put("/api/v1/settings", json={"settings": {"tech_log_retention_days": 0}})
        assert r.status_code == 400  # borne (1, None) rejetée


# ---------- Câblage : le moteur journalise (engine + source.query + ai.call) ----------


async def test_engine_ecrit_dans_le_journal_technique(engine):
    entries = engine.techlog.read(limit=50)
    events = [e["event"] for e in entries]
    assert "engine.setup" in events  # setup() journalise


async def test_source_query_journalisee_avec_duree(engine):
    """T3.13 : chaque requête source est chronométrée dans le journal technique."""
    from osia.tasks import TaskContext, handle_source_query

    inv = await make_investigation(engine, objective="obj")
    branches = await engine.repo.list_branches(inv["id"])
    task = await engine.repo.insert_task(
        investigation_id=inv["id"], branch_id=branches[0]["id"], kind="source_query",
        payload={"query": "test query", "connector_id": "simulated.web"}, depth=0, priority=10,
    )
    await handle_source_query(task, TaskContext(engine=engine))
    entries = [e for e in engine.techlog.read(limit=200) if e.get("event") == "source.query"]
    assert len(entries) == 1
    e = entries[0]
    assert e["investigation_id"] == inv["id"] and e["task_id"] == task["id"] and e["op_id"]
    assert isinstance(e["duration_ms"], int) and e["duration_ms"] >= 0
    assert e["detail"]["connector_id"] == "simulated.web" and e["detail"]["http_status"] == 200
