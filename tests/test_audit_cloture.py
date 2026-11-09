"""Vérification ciblée de clôture (commentaire #6713226112 sur l'issue #17, commit 7ec5ea3).

- EXEC-03 : frontend web facultatif — vrai choix d'activation (`web_ui_enabled` /
  `osia serve --no-web-ui` / `create_app(web_ui=False)`) : aucune route ni asset web servis,
  API pleinement servie, protections serveur (auth) conservées.
- EXEC-06 : notification de version livrée — `version.py` (check best-effort via le
  NetworkGuard, jamais d'exception), endpoint `/api/v1/system/version`, CLI
  `osia version [--check]`, check au démarrage du serveur.
"""

import hashlib
import json
import socket

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.cli import main as cli_main
from osia.config import Settings
from osia.netguard import NetworkGuard
from osia.version import __version__, fetch_latest_version, is_newer


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1")


# ---------- EXEC-03 : frontend facultatif ----------


async def test_exec03_web_ui_disabled_serves_no_web_routes_but_full_api(engine):
    app = create_app(engine, web_ui=False)
    async with await _client(app) as client:
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/static/app.js")).status_code == 404
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__


async def test_exec03_web_ui_enabled_by_default(engine):
    app = create_app(engine)
    async with await _client(app) as client:
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/static/app.js")).status_code == 200


async def test_exec03_web_ui_disabled_keeps_server_auth(engine):
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"secret").hexdigest()
    app = create_app(engine, web_ui=False)
    async with await _client(app) as client:
        # aucune route web, même sans auth
        assert (await client.get("/")).status_code == 404
        # l'API reste protégée en mode serveur
        assert (await client.get("/api/v1/health")).status_code == 401
        r = await client.get("/api/v1/health", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 200
    engine.settings.mode = "desktop"


def test_exec03_web_ui_setting_from_env(monkeypatch):
    monkeypatch.delenv("OSIA_WEB_UI_ENABLED", raising=False)
    assert Settings.from_env().web_ui_enabled is True
    monkeypatch.setenv("OSIA_WEB_UI_ENABLED", "0")
    assert Settings.from_env().web_ui_enabled is False
    monkeypatch.setenv("OSIA_WEB_UI_ENABLED", "1")
    assert Settings.from_env().web_ui_enabled is True


# ---------- EXEC-06 : notification de version ----------


async def test_exec06_fetch_latest_version_parses_and_never_raises(monkeypatch):
    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    monkeypatch.setattr(NetworkGuard, "_default_resolver", staticmethod(resolve))

    async def ok(url, ctx=None):
        return 200, {"content-type": "application/json"}, json.dumps({"info": {"version": "9.9.9"}}).encode()

    assert await fetch_latest_version(fetch_fn=ok) == "9.9.9"

    async def ko_status(url, ctx=None):
        return 500, {}, b"err"

    assert await fetch_latest_version(fetch_fn=ko_status) is None

    async def ko_json(url, ctx=None):
        return 200, {}, b"<html>not json</html>"

    assert await fetch_latest_version(fetch_fn=ko_json) is None

    async def boom(url, ctx=None):
        raise OSError("réseau coupé")

    assert await fetch_latest_version(fetch_fn=boom) is None


def test_exec06_is_newer():
    assert is_newer("0.2.0") is True
    assert is_newer("0.1.0") is False
    assert is_newer(None) is False
    assert is_newer("0.1.0-rc1") is False


async def test_exec06_api_system_version_endpoint(engine):
    engine.latest_version = "9.9.9"
    app = create_app(engine)
    async with await _client(app) as client:
        r = await client.get("/api/v1/system/version")
        assert r.status_code == 200
        body = r.json()
        assert body["current"] == __version__
        assert body["latest"] == "9.9.9"
        assert body["update_available"] is True
        assert body["check_enabled"] is True


def test_exec06_cli_version_and_check(monkeypatch, capsys):
    assert cli_main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__

    async def fake_fetch(url=..., fetch_fn=None):
        return "9.9.9"

    monkeypatch.setattr("osia.version.fetch_latest_version", fake_fetch)
    assert cli_main(["version", "--check"]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {"current": __version__, "latest": "9.9.9", "update_available": True}
