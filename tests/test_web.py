import hashlib
import pathlib
import shutil
import subprocess

from httpx import ASGITransport, AsyncClient

from osia.api import create_app

from conftest import make_investigation


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_web_serves_index_and_assets(engine):
    async with await client_for(engine) as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        body = r.text
        assert 'id="app"' in body
        assert "/static/app.js" in body
        assert "/static/styles.css" in body
        assert "Content-Security-Policy" in body
        assert "default-src 'self'" in body
        for path, ct in [
            ("/static/app.js", "javascript"),
            ("/static/styles.css", "text/css"),
            ("/static/index.html", "text/html"),
        ]:
            r = await client.get(path)
            assert r.status_code == 200, path
            assert ct in r.headers["content-type"], path
        r = await client.get("/static/inexistant.js")
        assert r.status_code == 404
        for traversal in ("/static/..%2F..%2Fpyproject.toml", "/static/%2e%2e/%2e%2e/pyproject.toml", "/static/....//pyproject.toml"):
            r = await client.get(traversal)
            assert r.status_code == 404, traversal
            assert "pyproject" not in r.text


async def test_web_shell_public_but_api_protected_in_server_mode(engine):
    """Audit F11 / T5.7 / EXEC-05 : en mode serveur, le shell de connexion ('/' et
    '/static/*') est servi SANS jeton — un navigateur neuf charge la page et le formulaire
    de connexion sans header Authorization (les sous-ressources ne les reprennent pas).
    L'API, elle, reste protégée."""
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"secret").hexdigest()
    try:
        async with await client_for(engine) as client:
            # parcours réel d'un navigateur neuf : aucun header
            r = await client.get("/")
            assert r.status_code == 200
            assert 'id="app"' in r.text
            assert 'id="auth-dialog"' in r.text
            r = await client.get("/static/app.js")
            assert r.status_code == 200
            assert "javascript" in r.headers["content-type"]
            assert (await client.get("/static/styles.css")).status_code == 200
            # l'API reste protégée sans jeton
            assert (await client.get("/api/v1/investigations")).status_code == 401
            assert (await client.get("/api/v1/health")).status_code == 401
            # et accessible avec le jeton admin
            h = {"Authorization": "Bearer secret"}
            assert (await client.get("/api/v1/investigations", headers=h)).status_code == 200
    finally:
        engine.settings.mode = "desktop"
        engine.settings.auth_token_hash = None


async def test_web_login_exchanges_admin_token_for_revocable_session(engine):
    """Audit F11 / CON-05 : POST /api/v1/auth/login échange le jeton admin contre une session
    `sess_*` expirable et révocable ; la session ouvre l'API, le logout la révoque, et le
    jeton admin statique reste valable."""
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"secret").hexdigest()
    try:
        async with await client_for(engine) as client:
            r = await client.post("/api/v1/auth/login", json={"token": "mauvais"})
            assert r.status_code == 401
            r = await client.post("/api/v1/auth/login", json={"token": "secret"})
            assert r.status_code == 200
            sess = r.json()["session_token"]
            assert sess.startswith("sess_")
            h = {"Authorization": "Bearer " + sess}
            assert (await client.get("/api/v1/investigations", headers=h)).status_code == 200
            sessions = await client.get("/api/v1/auth/sessions", headers=h)
            assert sessions.status_code == 200 and len(sessions.json()) >= 1
            r = await client.post("/api/v1/auth/logout", headers=h)
            assert r.status_code == 200 and r.json()["revoked"] is True
            assert (await client.get("/api/v1/investigations", headers=h)).status_code == 401
            # le jeton admin statique n'est pas révoqué par le logout d'une session
            h = {"Authorization": "Bearer secret"}
            assert (await client.get("/api/v1/investigations", headers=h)).status_code == 200
    finally:
        engine.settings.mode = "desktop"
        engine.settings.auth_token_hash = None


async def test_web_pages_available_while_investigation_runs(engine):
    async with await client_for(engine) as client:
        inv = await make_investigation(engine, title="web")
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/static/app.js")).status_code == 200
        r = await client.get(f"/api/v1/investigations/{inv['id']}/graph")
        assert r.status_code == 200
        r = await client.get(f"/api/v1/investigations/{inv['id']}/events")
        assert r.status_code == 200


async def test_import_apply_accepts_binary_upload(engine):
    """Le client web importe par upload binaire (évolution compatible de /api/v1/import/apply)."""
    async with await client_for(engine) as client:
        inv = await make_investigation(engine, title="import-web")
        r = await client.post(
            f"/api/v1/investigations/{inv['id']}/export",
            json={"format": "osia", "include_proofs": False},
        )
        assert r.status_code == 201
        export_id = r.json()["export_id"]
        archive_name = next(f["file"] for f in r.json()["files"] if f["file"].endswith(".osia"))
        rd = await client.get(f"/api/v1/exports/{export_id}/download?file={archive_name}")
        assert rd.status_code == 200
        r2 = await client.post(
            "/api/v1/import/apply?mode=add&on_conflict=fail",
            content=rd.content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r2.status_code == 201
        invs = await client.get("/api/v1/investigations")
        assert sum(1 for i in invs.json() if i["title"] == "import-web") == 2
        r3 = await client.post("/api/v1/import/apply", content=b"", headers={"Content-Type": "application/json"})
        assert r3.status_code == 400
        r4 = await client.post("/api/v1/import/apply", content=b"{pas json", headers={"Content-Type": "application/json"})
        assert r4.status_code == 400
        r5 = await client.post("/api/v1/import/apply", json={"mode": "add"})
        assert r5.status_code == 400


async def test_web_settings_view_wired_to_existing_api(engine):
    """La page de paramètres est servie avec le formulaire IA et les autres réglages.
    La saisie des clés passe par l'API fournisseur dédiée, qui n'expose pas leurs valeurs."""
    async with await client_for(engine) as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert 'href="#/parametres"' in r.text
        js = await client.get("/static/app.js")
        assert js.status_code == 200
        for needle in (
            "renderSettings",
            "'/parametres'",
            "/api/v1/ai/providers",
            "/api/v1/ai/providers/",
            "/api/v1/ai/selection/",
            "/api/v1/ai/fallback",
            "/api/v1/settings",
            "/api/v1/profiles",
            "/api/v1/connectors",
            "/api/v1/secrets",
        ):
            assert needle in js.text, needle
        assert "/api/v1/secrets/" not in js.text
        r = await client.get("/api/v1/ai/providers")
        assert r.status_code == 200 and isinstance(r.json()["providers"], list)
        r = await client.get("/api/v1/settings")
        assert r.status_code == 200 and "paid_calls_enabled" in r.json()["settings"]
        r = await client.get("/api/v1/connectors")
        assert r.status_code == 200 and isinstance(r.json(), list)


def test_app_js_smoke_node():
    """Vérifie l'accueil et le parcours du formulaire IA avec un DOM et une API simulés."""
    if shutil.which("node") is None:
        return
    app_js = pathlib.Path(__file__).parent.parent / "src" / "osia" / "web" / "app.js"
    script = ["node", str(pathlib.Path(__file__).parent / "js_smoke_app.js"), str(app_js)]
    for args, expected in (([], "Nouvelle investigation"), (["--settings"], "Mistral API · model-from-catalogue")):
        p = subprocess.run(script + args, capture_output=True, text=True)
        assert p.returncode == 0 and "SCRIPT OK" in p.stdout, p.stdout + p.stderr
        assert expected in p.stdout
