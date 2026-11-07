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


async def test_web_requires_auth_in_server_mode(engine):
    """T5.7 / EXEC-05 : en mode serveur, '/' et '/static/*' exigent le jeton comme l'API."""
    engine.settings.mode = "server"
    engine.settings.auth_token_hash = hashlib.sha256(b"secret").hexdigest()
    try:
        async with await client_for(engine) as client:
            assert (await client.get("/")).status_code == 401
            assert (await client.get("/static/app.js")).status_code == 401
            assert (await client.get("/static/styles.css")).status_code == 401
            h = {"Authorization": "Bearer secret"}
            r = await client.get("/", headers=h)
            assert r.status_code == 200
            assert 'id="app"' in r.text
            r = await client.get("/static/app.js", headers=h)
            assert r.status_code == 200
            assert "javascript" in r.headers["content-type"]
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
    """Le client web importe par upload binaire (Ã©volution compatible de /api/v1/import/apply)."""
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


def test_app_js_smoke_node():
    """app.js se charge sans exception avec un DOM simulÃ© et rend la vue d'accueil."""
    if shutil.which("node") is None:
        return
    app_js = pathlib.Path(__file__).parent.parent / "src" / "osia" / "web" / "app.js"
    p = subprocess.run(
        ["node", str(pathlib.Path(__file__).parent / "js_smoke_app.js"), str(app_js)],
        capture_output=True,
        text=True,
    )
    assert "SCRIPT OK" in p.stdout, p.stdout + p.stderr
    assert "Nouvelle investigation" in p.stdout
