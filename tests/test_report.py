import pathlib

from conftest import make_investigation


async def _seed(engine, inv_id, name="ACME"):
    branch = (await engine.repo.list_branches(inv_id))[0]
    proof = await engine.filestore.store_proof(
        investigation_id=inv_id, content=b"preuve", source_url="https://exemple.test/secret-doc", media_type="text/plain"
    )
    a = await engine.graph.upsert_entity(inv_id, kind="organisation", data={"name": name}, identifiers={"siren": "123456789"})
    await engine.graph.add_assertion(inv_id, branch_id=branch["id"], statement=f"{name} existe", proof_ids=[proof["proof_ref_id"]], decisive=True)
    return proof, a


async def test_html_autonome_no_network_no_active_content(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"], name="<script>alert(1)</script>")
    html = await engine.report.build(inv["id"])
    out = tmp_path / "rapport.html"
    out.write_text(html, encoding="utf-8")
    text = out.read_text(encoding="utf-8")
    assert 'id="osia-data"' in text
    for forbidden in ("<script src", "<link ", "fetch(", "XMLHttpRequest", "WebSocket", "import("):
        assert forbidden not in text, forbidden
    assert "<script>alert(1)</script>" not in text
    assert "<\\/script>" in text
    assert "ACME" not in text or "alert" in text


async def test_html_exclusions_are_really_absent(engine, tmp_path):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    html_with = await engine.report.build(inv["id"], include_proofs_meta=True)
    assert "https://exemple.test/secret-doc" in html_with
    html_without = await engine.report.build(inv["id"], include_proofs_meta=False)
    assert "https://exemple.test/secret-doc" not in html_without
    assert "secret-doc" not in html_without
    assert html_without.count("osia-data") >= 1


async def test_html_partial_warns(engine):
    inv = await make_investigation(engine)
    await _seed(engine, inv["id"])
    html = await engine.report.build(inv["id"], exclusions={"events"})
    assert "Export partiel" in html


async def test_html_embedded_js_renders_and_escapes(engine, tmp_path):
    import shutil
    import subprocess

    inv = await make_investigation(engine)
    await _seed(engine, inv["id"], name="<img src=x onerror=alert(1)>")
    html = await engine.report.build(inv["id"])
    out = tmp_path / "rapport.html"
    out.write_text(html, encoding="utf-8")
    if shutil.which("node") is None:
        return
    import pathlib
    p = subprocess.run(["node", str(pathlib.Path(__file__).parent / "js_smoke.js"), str(out)], capture_output=True, text=True)
    assert "SCRIPT OK" in p.stdout, p.stdout
    assert "<img src=x onerror=" not in p.stdout
    assert "&lt;img src=x onerror=alert(1)&gt;" in p.stdout
