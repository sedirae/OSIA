import hashlib
import json
import stat
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.config import ConfigError, Settings
from osia.security import ensure_self_signed_cert, ensure_server_credentials


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1")


def server_engine(engine, token: bytes = b"secret"):
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(token).hexdigest()
    return engine


async def test_server_mode_requires_auth_everywhere(engine):
    """CON-05 / T5.7 / EXEC-05 : en mode serveur, toutes les routes API exigent un credential,
    même sans frontend. Audit F11 : le shell web ('/' et '/static/*') reste PUBLIC (formulaire
    de connexion, aucune donnée sensible) pour permettre la connexion depuis un navigateur ;
    seules les données (/api/v1/*) sont protégées. Les refus sont audités (T5.9) sans secret."""
    server_engine(engine)
    async with await client_for(engine) as client:
        for path in ["/api/v1/health", "/api/v1/profiles", "/api/v1/investigations", "/api/v1/auth/sessions"]:
            r = await client.get(path)
            assert r.status_code == 401, path
        # shell de connexion public (F11) : la page et ses assets se chargent sans header
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/static/app.js")).status_code == 200
        entries = engine.audit.read(limit=50)
        assert any(e["action"] == "auth.denied" and e["outcome"] == "failure" for e in entries)
        assert all("secret" not in json.dumps(e) for e in entries)


async def test_login_session_flow(engine):
    """CON-05 : login admin -> session expirable/révocable ; le jeton statique reste accepté."""
    server_engine(engine)
    async with await client_for(engine) as client:
        r = await client.post("/api/v1/auth/login", json={"token": "wrong"})
        assert r.status_code == 401
        r = await client.post("/api/v1/auth/login", json={"token": "secret"})
        assert r.status_code == 200
        session = r.json()["session_token"]
        assert session.startswith("sess_")
        h = {"Authorization": f"Bearer {session}"}
        assert (await client.get("/api/v1/health", headers=h)).status_code == 200
        # jeton statique administrateur toujours accepté (rétrocompat)
        assert (await client.get("/api/v1/health", headers={"Authorization": "Bearer secret"})).status_code == 200
        # liste des sessions actives (sans hash)
        r = await client.get("/api/v1/auth/sessions", headers=h)
        assert r.status_code == 200 and len(r.json()) == 1
        assert "token_hash" not in json.dumps(r.json())
        # logout révoque la session
        assert (await client.post("/api/v1/auth/logout", headers=h)).status_code == 200
        assert (await client.get("/api/v1/health", headers=h)).status_code == 401
        # l'audit trace login succès/échec et logout, sans le secret
        actions = [e["action"] for e in engine.audit.read(limit=50)]
        assert "auth.login" in actions and "auth.logout" in actions
        assert all("secret" not in json.dumps(e) for e in engine.audit.read(limit=50))


async def test_login_refused_in_desktop_mode(engine):
    """T1 : en mode desktop (liaison locale), aucune authentification distante n'est requise."""
    async with await client_for(engine) as client:
        r = await client.post("/api/v1/auth/login", json={"token": "x"})
        assert r.status_code == 400
        assert (await client.get("/api/v1/health")).status_code == 200


async def test_session_expiry(engine):
    """CON-05 : une session expirée n'est plus valide."""
    server_engine(engine)
    engine.sessions.ttl = timedelta(hours=-1)
    token, _ = await engine.sessions.create()
    assert not await engine.sessions.validate(token)


async def test_validate_runtime_blocks_implicit_exposure():
    """CON-05 (T1/T5.7) : desktop non local et serveur exposé sans TLS sont refusés."""
    with pytest.raises(ConfigError):
        Settings(mode="desktop", listen_host="0.0.0.0").validate_runtime()
    with pytest.raises(ConfigError):
        Settings(mode="server", listen_host="0.0.0.0").validate_runtime()
    Settings(mode="server", listen_host="0.0.0.0", tls_autogen=True).validate_runtime()
    Settings(mode="server", listen_host="0.0.0.0", tls_certfile="c.pem", tls_keyfile="k.pem").validate_runtime()
    Settings(mode="server", listen_host="127.0.0.1").validate_runtime()
    Settings(mode="desktop", listen_host="127.0.0.1").validate_runtime()


async def test_audit_file_permissions_and_scrub(engine):
    """T5.9 : journal d'audit en 0600, clés sensibles masquées."""
    engine.audit.log("auth.login", "success", detail={"token": "secret-value", "note": "ok"})
    path = engine.audit.path
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    content = path.read_text(encoding="utf-8")
    assert "secret-value" not in content
    assert "***" in content
    assert "ok" in content


async def test_paths_ensure_restricts_permissions(engine):
    """CON-05 / D6 : répertoires sensibles en 0700."""
    paths = engine.settings.paths
    for d in (paths.config_dir, paths.data_dir, paths.log_dir, paths.backup_dir, paths.proofs_dir):
        assert d.exists()
        assert stat.S_IMODE(d.stat().st_mode) == 0o700, d


async def test_tls_autogen_creates_cert_and_key_0600(tmp_path):
    """CON-05 / T5.7 : certificat auto-signé local, clé 0600."""
    cert, key = ensure_self_signed_cert(tmp_path / "tls")
    assert cert.exists() and key.exists()
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(cert.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "tls").stat().st_mode) == 0o700


async def test_ensure_server_credentials_generates_token_once(engine):
    """CON-05 : en mode serveur sans jeton configuré, un jeton est généré (hash en base,
    clair dans un fichier 0600), audité sans secret, et non regénéré ensuite."""
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = None
    token = await ensure_server_credentials(engine)
    assert token
    token_file = engine.settings.paths.config_dir / "auth_token"
    assert token_file.exists()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert token_file.read_text(encoding="utf-8").strip() == token
    stored = await engine.repo.get_setting("auth_token_hash")
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert await ensure_server_credentials(engine) is None  # pas de regénération
    entries = engine.audit.read(limit=10)
    assert any(e["action"] == "auth.token.issued" for e in entries)
    assert all(token not in json.dumps(e) for e in entries)
