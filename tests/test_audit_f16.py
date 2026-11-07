"""Audit #17 F16 (recette/distribution/confidentialité) + réserves P3 des audits PR#18/#19/#21.

- F16 : le test budgétaire concurrent utilise le profil "approfondi" (l'override 10 n'est
  plus clampé à 5 par le profil "rapide") ; secrets non persistés par défaut (T5.5/D2) ;
  aucun DNS public réel dans les tests réseau (resolver injecté) ; suffixes publics rejetés
  dans la politique réseau ; dépendances bornées (pyproject) ; extra web = paquet de base.
- P3 PR#18 : entrées de manifeste malformées -> ArchiveError (jamais KeyError/CryptoError),
  lecture unique des entrées (preloaded), sessions HTTP poolées.
- P3 PR#19 : BudgetView additif documenté + scope branche ; libération des réservations
  DANS la transaction du stop/suspend (pas de réservation orpheline après crash).
"""

import asyncio
import hashlib
import json
import socket
import zipfile

import pytest

from osia.config import Settings
from osia.exchange.archive import MANIFEST, ArchiveError, extract_payload, read_and_verify
from osia.exchange.crypto import ArchiveCrypto
from osia.models import CreateBranchRequest, StopReason
from osia.netguard import NetworkGuard, NetworkPolicy, PinnedTarget
from osia.nethttp import SessionPool, pool_key
from osia.policies.limits import limits_from_record

from conftest import make_investigation


# ---------- F16 : profil "approfondi" (le clamp du profil "rapide" cassait le scénario) ----------


async def test_f16_override_cap_not_clamped_on_profil_approfondi(engine):
    inv = await make_investigation(engine, profile_id="approfondi", limits={"max_cost_cents": 10})
    rec = await engine.repo.get_investigation(inv["id"])
    assert limits_from_record(rec).max_cost_cents == 10
    # Contraste documenté : sur le profil par défaut "rapide" (plafond 5), le même override
    # est clampé à 5 — c'est ce clamp qui rendait l'ancien test incohérent.
    inv2 = await make_investigation(engine, limits={"max_cost_cents": 10})
    rec2 = await engine.repo.get_investigation(inv2["id"])
    assert limits_from_record(rec2).max_cost_cents == 5


# ---------- F16 : secrets en mémoire par défaut (T5.5 / D2) ----------


def test_f16_secrets_persist_default_false(monkeypatch):
    monkeypatch.delenv("OSIA_SECRETS_PERSIST", raising=False)
    assert Settings().secrets_persist is False
    assert Settings.from_env().secrets_persist is False
    monkeypatch.setenv("OSIA_SECRETS_PERSIST", "1")
    assert Settings.from_env().secrets_persist is True
    monkeypatch.setenv("OSIA_SECRETS_PERSIST", "0")
    assert Settings.from_env().secrets_persist is False


# ---------- F16 : aucun DNS public réel quand un resolver est injecté ----------


async def test_f16_guarded_request_with_injected_resolver_never_calls_real_dns(monkeypatch):
    def boom(self, host, port, *args, **kwargs):
        raise AssertionError(f"résolution DNS réelle appelée pour {host!r}")

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", boom)

    async def fake_resolver(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    guard = NetworkGuard(
        NetworkPolicy(allowed_domains={"recherche-entreprises.api.gouv.fr"}, min_interval_seconds=0),
        resolver=fake_resolver,
    )

    async def fetch(url):
        return 200, {"content-type": "application/json"}, b"{}"

    status, _, _ = await guard.guarded_request(fetch, "https://recherche-entreprises.api.gouv.fr/x")
    assert status == 200


# ---------- P3 PR#21 : suffixe public rejeté dans la politique réseau ----------


def test_f16_netguard_rejects_public_suffix_in_allowlist():
    with pytest.raises(ValueError):
        NetworkPolicy(allowed_domains={"co.uk"})
    with pytest.raises(ValueError):
        NetworkPolicy(denied_domains={"com.au"})
    policy = NetworkPolicy(allowed_domains={"example.test"})
    assert policy.domain_allowed("example.test")
    assert policy.domain_allowed("sub.example.test")
    assert not policy.domain_allowed("notexample.test")


# ---------- P3 PR#18 : manifeste malformé -> ArchiveError (jamais KeyError/CryptoError) ----------


def _craft(dest, files, entries):
    manifest = {
        "format": "osia-archive",
        "format_version": "1.0",
        "encrypted": False,
        "scope": {},
        "counts": {},
        "warnings": [],
        "files": files,
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(MANIFEST, json.dumps(manifest))
        for name, content in entries.items():
            zf.writestr(name, content)
    return dest


def test_f16_extract_payload_missing_path_raises_archive_error(tmp_path):
    dest = _craft(tmp_path / "bad.osia", [{"sha256": "ab" * 32}], {"data/investigations.json": b"[]"})
    with zipfile.ZipFile(dest) as zf:
        manifest = json.loads(zf.read(MANIFEST))
        with pytest.raises(ArchiveError):
            extract_payload(zf, manifest, encrypted=False)


def test_f16_extract_payload_encrypted_missing_nonce_raises_archive_error(tmp_path):
    content = b'[{"id":"i1"}]'
    files = [{"path": "data/investigations.json", "sha256": hashlib.sha256(content).hexdigest(), "enc": "a1b2c3.enc"}]
    dest = _craft(tmp_path / "bad2.osia", files, {"a1b2c3.enc": b"\x00\x01"})
    with zipfile.ZipFile(dest) as zf:
        manifest = json.loads(zf.read(MANIFEST))
        crypto = ArchiveCrypto("phrase")
        with pytest.raises(ArchiveError):
            extract_payload(zf, manifest, encrypted=True, key=b"k" * 32, crypto=crypto)


def test_f16_read_and_verify_single_pass_then_preloaded_extract(tmp_path):
    content = b'{"id":"i1"}\n'
    sha = hashlib.sha256(content).hexdigest()
    files = [{"path": "data/investigations.jsonl", "sha256": sha, "size_bytes": len(content)}]
    dest = _craft(tmp_path / "ok.osia", files, {"data/investigations.jsonl": content})
    meta, manifest, zf, crypto, raw = read_and_verify(dest)
    try:
        assert set(raw) == {"data/investigations.jsonl"}
        payload, proofs = extract_payload(zf, manifest, encrypted=False, preloaded=raw)
        assert payload["investigations"] == [{"id": "i1"}]
        assert proofs == {}
    finally:
        zf.close()


# ---------- P3 PR#19 : BudgetView scope branche + libération atomique au stop ----------


async def test_f16_budget_view_branch_scope(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine, profile_id="approfondi", limits={"max_cost_cents": 100})
    branch = await engine.orchestrator.create_branch(
        inv["id"],
        CreateBranchRequest(objective="approfondir", explicit_acceptance=True, limits={"max_cost_cents": 30}),
    )
    op = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    await engine.budgets.reserve(
        idempotency_key="br1", investigation_id=inv["id"], op_id=op["id"], amount_cents=7, branch_id=branch["id"]
    )
    view = await engine.budgets.budget_view(inv["id"], branch_id=branch["id"])
    assert view.caps["branch"] == 30
    assert view.reserved_cents == 7
    # available = min(cap - used) sur chaque scope : branche 30-7=23, investigation 100-7=93, global 500-7=493
    assert view.available_cents == 23
    view_all = await engine.budgets.budget_view(inv["id"])
    assert "branch" not in view_all.caps


async def test_f16_stop_releases_reservations_atomically(engine):
    await engine.repo.set_setting("paid_calls_enabled", True)
    inv = await make_investigation(engine, profile_id="approfondi", limits={"max_cost_cents": 100})
    op = await engine.repo.insert_op(investigation_id=inv["id"], kind="ai_call", target="simulated:simulated-1")
    res = await engine.budgets.reserve(
        idempotency_key="st1", investigation_id=inv["id"], op_id=op["id"], amount_cents=9
    )
    await engine.repo.set_op_state(op["id"], "reserved", reservation_id=res["id"])
    await engine.orchestrator.stop(inv["id"], StopReason.USER)
    state = await engine.pool.fetchval("SELECT state FROM reservations WHERE id = $1", res["id"])
    assert state == "released"
    kinds = await engine.pool.fetch("SELECT kind FROM ledger WHERE reservation_id = $1 ORDER BY id", res["id"])
    assert [k["kind"] for k in kinds] == ["reserved", "released"]
    view = await engine.budgets.budget_view(inv["id"])
    assert view.reserved_cents == 0


# ---------- P3 PR#18 : pool de sessions HTTP réutilisées ----------


async def test_f16_session_pool_reuses_sessions():
    pool = SessionPool()
    try:
        s1 = await pool.session("k1")
        s2 = await pool.session("k1")
        assert s1 is s2
        s3 = await pool.session("k2")
        assert s3 is not s1
    finally:
        await pool.close()


def test_f16_pool_key_separates_pinned_and_unpinned():
    # Audit PR#24 P3-c : la clé inclut le statut épinglé et les IPs validées — une session
    # non épinglée ne doit jamais être réutilisée pour un appel épinglé (anti-TOCTOU).
    pinned = PinnedTarget(host="a.test", port=443, ips=["192.0.2.1"])
    pinned2 = PinnedTarget(host="a.test", port=443, ips=["192.0.2.2"])
    assert pool_key(None) == "default"
    assert pool_key(pinned) != pool_key(None)
    assert pool_key(pinned) != pool_key(pinned2)
    assert pool_key(pinned, fallback="x") == pool_key(pinned)
