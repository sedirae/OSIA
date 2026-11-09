"""CON-07/CON-08 (B1/B2/B3/B7, T3.8, T5) : connecteurs réels V1.2, contrat HTTP gardé par le
NetworkGuard, contrôles sémantiques et surveillance de santé (B7 §9.1).

Tous les tests utilisent des fixtures JSON injectées via `fetch_fn` : aucun appel réseau
(AGENTS.md : connecteurs simulés en test, aucun appel externe réel)."""

import io
import json
import socket

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.connectors.base import FetchRequest
from osia.connectors.health import ConnectorHealthChecker, HealthState
from osia.connectors.real import (
    BodaccConnector,
    GleifConnector,
    RechercheEntreprisesConnector,
    WebUrlConnector,
    build_real_connectors,
    extract_text_from_html,
    extract_text_from_pdf,
)
from osia.connectors.registry import ConnectorRegistry
from osia.netguard import NetworkDeny, NetworkGuard, NetworkPolicy

RECHERCHE_FIXTURE = {
    "results": [
        {
            "siren": "552100554",
            "nom_complet": "ELECTRICITE DE FRANCE",
            "etat_administratif": "A",
            "nature_juridique": "5710",
            "activite_principale": "35.11Z",
            "siege": {"adresse": "22-30 AVENUE DE WAGRAM 75008 PARIS"},
        }
    ],
    "total_results": 1,
    "page": 1,
    "per_page": 5,
}

GLEIF_FIXTURE = {
    "data": [
        {
            "id": "969500T9EZF3XENR1R42",
            "attributes": {
                "entity": {
                    "legalName": {"value": "ELECTRICITE DE FRANCE"},
                    "legalAddress": {"country": "FR"},
                }
            },
        }
    ],
    "meta": {"pagination": {"total": 1}},
}

BODACC_FIXTURE = {"results": [{"id": "A-2026-001", "titre": "Avis BODACC"}], "total": 1}


def fake_fetch(payload, status=200, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    async def fetch(url):
        return status, headers or {"content-type": "application/json"}, body

    return fetch


def recording_fetch(payload, calls, status=200):
    body = json.dumps(payload).encode("utf-8")

    async def fetch(url):
        calls.append(url)
        return status, {"content-type": "application/json"}, body

    return fetch


def make_pdf(text: str) -> bytes:
    """PDF minimal textuel fabriqué à la main (fixture hors ligne pour l'extraction pypdf)."""
    content = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


# ---------- Normalisation et contrat (B3, CON-07) ----------


async def test_recherche_entreprises_normalisation():
    c = RechercheEntreprisesConnector(fetch_fn=fake_fetch(RECHERCHE_FIXTURE))
    res = await c.fetch(FetchRequest(query="EDF"))
    payload = json.loads(res.content)
    assert payload["total_results"] == 1
    assert payload["results"][0]["siren"] == "552100554"
    assert payload["results"][0]["nom_complet"] == "ELECTRICITE DE FRANCE"
    assert res.provenance.source_id == "gouv.recherche-entreprises"
    assert res.provenance.http_status == 200
    assert "q=EDF" in res.provenance.url
    assert c.validate_response(payload) == []


async def test_gleif_lei_vs_nom():
    calls = []
    c = GleifConnector(fetch_fn=recording_fetch(GLEIF_FIXTURE, calls))
    res = await c.fetch(FetchRequest(query="969500T9EZF3XENR1R42"))
    assert "filter%5Blei%5D=969500T9EZF3XENR1R42" in calls[-1]
    payload = json.loads(res.content)
    assert payload["results"][0]["lei"] == "969500T9EZF3XENR1R42"
    assert payload["results"][0]["legal_name"] == "ELECTRICITE DE FRANCE"
    assert payload["results"][0]["country"] == "FR"

    await c.fetch(FetchRequest(query="EDF"))
    assert "filter%5Bentity.legalName%5D=EDF" in calls[-1]


async def test_bodacc_normalisation():
    c = BodaccConnector(fetch_fn=fake_fetch(BODACC_FIXTURE))
    res = await c.fetch(FetchRequest(query="EDF"))
    payload = json.loads(res.content)
    assert payload["total"] == 1
    assert payload["results"][0]["id"] == "A-2026-001"
    assert c.validate_response(payload) == []


async def test_validate_response_detecte_structure_invalide():
    """B7 §9.1 : une HTTP 200 ne suffit pas, la structure normalisée doit être contrôlée."""
    c = RechercheEntreprisesConnector(fetch_fn=fake_fetch({}))
    assert c.validate_response({"results": [{"siren": None}]}) != []
    assert c.validate_response({"pas_results": True}) != []
    g = GleifConnector(fetch_fn=fake_fetch({}))
    assert g.validate_response({"results": [{"lei": None}]}) != []
    assert g.validate_response({"data": [{"id": "x"}]}) != []  # forme brute non normalisée


async def test_provenance_url_encodee_et_fidele():
    """T5.6 : l'URL de provenance stockée avec la preuve est bien formée (urlencode)
    même pour une requête avec caractères réservés, et reflète la requête réelle."""
    c = RechercheEntreprisesConnector(fetch_fn=fake_fetch(RECHERCHE_FIXTURE))
    res = await c.fetch(FetchRequest(query="A & B"))
    assert "q=A+%26+B" in res.provenance.url

    g = GleifConnector(fetch_fn=fake_fetch(GLEIF_FIXTURE))
    res_g = await g.fetch(FetchRequest(query="969500T9EZF3XENR1R42"))
    assert "filter%5Blei%5D=969500T9EZF3XENR1R42" in res_g.provenance.url


async def test_normalisation_tolere_champs_null():
    """B7 §9.1 : une réponse mal formée (champs null) produit une structure contrôlable,
    pas un crash — validate_response reste applicable."""
    g = GleifConnector(fetch_fn=fake_fetch({"data": [{"id": "x", "attributes": {"entity": {"legalName": None, "legalAddress": None}}}]}))
    res = await g.fetch(FetchRequest(query="EDF"))
    payload = json.loads(res.content)
    assert payload["results"] == [{"lei": "x", "legal_name": None, "country": None}]
    assert g.validate_response(payload) == []

    b = BodaccConnector(fetch_fn=fake_fetch({"results": None, "meta": None}))
    res_b = await b.fetch(FetchRequest(query="EDF"))
    assert json.loads(res_b.content) == {"query": "EDF", "total": 0, "results": []}

    r = RechercheEntreprisesConnector(fetch_fn=fake_fetch({"results": None, "total_results": None}))
    payload_r = json.loads((await r.fetch(FetchRequest(query="EDF"))).content)
    assert payload_r["results"] == [] and payload_r["total_results"] == 0


# ---------- NetworkGuard (T5.4) ----------


async def test_netguard_refuse_domaine_non_autorise():
    guard = NetworkGuard(NetworkPolicy(allowed_domains={"ok.test"}, min_interval_seconds=0))
    c = WebUrlConnector(netguard=guard, fetch_fn=fake_fetch(b"<html></html>", headers={"content-type": "text/html"}))
    with pytest.raises(NetworkDeny):
        await c.fetch(FetchRequest(query="https://evil.test/page"))


async def test_tout_fetch_passe_par_le_guard():
    """Même une URL autorisée passe par guarded_request (rate limit, redirections, taille)."""
    seen = []

    async def fetch(url):
        seen.append(url)
        return 200, {"content-type": "application/json"}, json.dumps(RECHERCHE_FIXTURE).encode()

    # F16 : aucun DNS public réel dans un test présenté « hors ligne » — resolver injecté
    # (IP de documentation TEST-NET-1, RFC 5737), comme dans test_con06.
    async def fake_resolver(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    guard = NetworkGuard(
        NetworkPolicy(allowed_domains={"recherche-entreprises.api.gouv.fr"}, min_interval_seconds=0),
        resolver=fake_resolver,
    )
    c = RechercheEntreprisesConnector(netguard=guard, fetch_fn=fetch)
    res = await c.fetch(FetchRequest(query="EDF"))
    assert res.provenance.http_status == 200
    assert seen and "recherche-entreprises.api.gouv.fr" in seen[0]


# ---------- Extraction web (B3) ----------


def test_extraction_html_filtre_scripts_et_styles():
    html = "<html><head><style>.x{color:red}</style></head><body><h1>Titre</h1><script>evil()</script><p>Bonjour</p></body></html>"
    text = extract_text_from_html(html)
    assert "Titre" in text and "Bonjour" in text
    assert "evil" not in text and "color" not in text


async def test_web_url_html_et_pdf():
    html = b"<html><body><p>Page publique</p><script>x()</script></body></html>"
    c = WebUrlConnector(fetch_fn=fake_fetch(html, headers={"content-type": "text/html; charset=utf-8"}))
    res = await c.fetch(FetchRequest(query="https://ok.test/page"))
    assert "Page publique" in res.extracted_text
    assert "x()" not in res.extracted_text

    pdf = make_pdf("Hello OSIA")
    c2 = WebUrlConnector(fetch_fn=fake_fetch(pdf, headers={"content-type": "application/pdf"}))
    res2 = await c2.fetch(FetchRequest(query="https://ok.test/doc.pdf"))
    assert res2.media_type == "application/pdf"
    assert "Hello OSIA" in res2.extracted_text
    assert extract_text_from_pdf(pdf) == "Hello OSIA"


# ---------- Surveillance de santé (B7 §9.1, CON-07/CON-08) ----------


def registry_with(**connectors):
    reg = ConnectorRegistry()
    for c in connectors.values():
        reg.register(c)
    return reg


async def test_health_operationnel():
    reg = registry_with(c=RechercheEntreprisesConnector(fetch_fn=fake_fetch(RECHERCHE_FIXTURE)))
    checker = ConnectorHealthChecker(reg)
    report = await checker.check("gouv.recherche-entreprises")
    assert report.state == HealthState.OPERATIONNEL
    assert report.http_status == 200
    assert checker.last_report("gouv.recherche-entreprises").state == HealthState.OPERATIONNEL


async def test_health_degrade_si_validation_echoue():
    """HTTP 200 mais structure invalide -> dégradé (B7 §9.1)."""
    reg = registry_with(c=RechercheEntreprisesConnector(fetch_fn=fake_fetch({"results": [{"nom": "x"}]})))
    checker = ConnectorHealthChecker(reg)
    report = await checker.check("gouv.recherche-entreprises")
    assert report.state == HealthState.DEGRADE
    assert report.validation_problems


async def test_health_degrade_si_reponse_200_non_json():
    """B7 §9.1 : une réponse 200 dont le corps n'est pas le JSON attendu est un problème
    de structure -> dégradé (pas une indisponibilité réseau -> suspendu)."""
    c = RechercheEntreprisesConnector(fetch_fn=fake_fetch(b"<html>page d'erreur</html>", headers={"content-type": "text/html"}))
    checker = ConnectorHealthChecker(registry_with(c=c))
    report = await checker.check("gouv.recherche-entreprises")
    assert report.state == HealthState.DEGRADE
    assert "structure inattendue" in report.detail


async def test_health_suspendu_si_indisponible_ou_desactive():
    async def boom(url):
        raise NetworkDeny("domaine_non_autorise", "evil.test")

    reg = registry_with(
        w=WebUrlConnector(fetch_fn=boom),
        g=GleifConnector(fetch_fn=fake_fetch(GLEIF_FIXTURE)),
    )
    reg.set_enabled("gleif.lei", False)
    checker = ConnectorHealthChecker(reg)
    r1 = await checker.check("web.url", probe_query="https://evil.test/")
    assert r1.state == HealthState.SUSPENDU
    assert "NetworkGuard" in r1.detail
    r2 = await checker.check("gleif.lei")
    assert r2.state == HealthState.SUSPENDU  # désactivé = retiré sans bloquer les autres (B-ACC-01)
    r3 = await checker.check("inconnu.x")
    assert r3.state == HealthState.SUSPENDU


async def test_health_suspendu_si_exception_reseau():
    async def timeout(url):
        raise TimeoutError("connexion expirée")

    reg = registry_with(c=RechercheEntreprisesConnector(fetch_fn=timeout))
    checker = ConnectorHealthChecker(reg)
    report = await checker.check("gouv.recherche-entreprises")
    assert report.state == HealthState.SUSPENDU
    assert "TimeoutError" in report.detail


async def test_health_obsolete_si_conditions_non_reverifiees():
    c = RechercheEntreprisesConnector(fetch_fn=fake_fetch(RECHERCHE_FIXTURE))
    c.manifest.last_checked = "2020-01-01"
    reg = registry_with(c=c)
    checker = ConnectorHealthChecker(reg)
    report = await checker.check("gouv.recherche-entreprises")
    assert report.state == HealthState.OBSOLETE
    assert "revérification" in report.detail


async def test_health_inconnu_sans_sonde_et_probe_manuelle():
    reg = registry_with(w=WebUrlConnector(fetch_fn=fake_fetch(b"<html><body><p>ok</p></body></html>", headers={"content-type": "text/html"})))
    checker = ConnectorHealthChecker(reg)
    r1 = await checker.check("web.url")
    assert r1.state == HealthState.INCONNU
    r2 = await checker.check("web.url", probe_query="https://ok.test/page")
    assert r2.state == HealthState.OPERATIONNEL


async def test_health_check_all():
    reg = registry_with(
        r=RechercheEntreprisesConnector(fetch_fn=fake_fetch(RECHERCHE_FIXTURE)),
        g=GleifConnector(fetch_fn=fake_fetch(GLEIF_FIXTURE)),
    )
    checker = ConnectorHealthChecker(reg)
    reports = await checker.check_all()
    assert {r.connector_id for r in reports} == {"gouv.recherche-entreprises", "gleif.lei"}
    assert all(r.state == HealthState.OPERATIONNEL for r in reports)


# ---------- Intégration moteur + API ----------


async def test_engine_enregistre_connecteurs_reels(engine):
    ids = {e["id"] for e in engine.registry.list()}
    assert {"gouv.recherche-entreprises", "gouv.bodacc", "gleif.lei", "web.url"} <= ids
    allowed = engine.netguard.policy.allowed_domains
    assert {"recherche-entreprises.api.gouv.fr", "api.gleif.org"} <= allowed
    assert engine.health is not None
    assert engine.registry.get("gouv.recherche-entreprises").netguard is engine.netguard


def _install_fake_fetch(engine):
    """Remplace le fetch réel des connecteurs enregistrés par des fixtures (hors ligne)."""

    def dispatch(url):
        if "recherche-entreprises" in url:
            return 200, {"content-type": "application/json"}, json.dumps(RECHERCHE_FIXTURE).encode()
        if "gleif" in url:
            return 200, {"content-type": "application/json"}, json.dumps(GLEIF_FIXTURE).encode()
        if "bodacc" in url:
            return 200, {"content-type": "application/json"}, json.dumps(BODACC_FIXTURE).encode()
        return 200, {"content-type": "text/html"}, b"<html><body><p>ok</p></body></html>"

    async def fetch(url):
        return dispatch(url)

    for entry in engine.registry.list():
        c = engine.registry.get(entry["id"])
        if hasattr(c, "fetch_fn"):
            c.netguard = None  # pas de DNS/réseau en test
            c.fetch_fn = fetch


async def test_api_health_routes(engine):
    _install_fake_fetch(engine)
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        r = await client.get("/api/v1/connectors")
        assert r.status_code == 200
        ids = {e["id"] for e in r.json()}
        assert "gouv.recherche-entreprises" in ids

        r = await client.get("/api/v1/connectors/gouv.recherche-entreprises/health")
        assert r.status_code == 200
        assert r.json()["state"] == "inconnu"  # aucun contrôle avant le premier health-check

        r = await client.post("/api/v1/connectors/health-check", json={"connector_id": "gouv.recherche-entreprises"})
        assert r.status_code == 200
        report = r.json()["reports"][0]
        assert report["state"] == "operationnel"
        assert report["http_status"] == 200

        r = await client.get("/api/v1/connectors/gouv.recherche-entreprises/health")
        assert r.json()["state"] == "operationnel"

        r = await client.post("/api/v1/connectors/health-check", json={})
        assert r.status_code == 200
        states = {rep["connector_id"]: rep["state"] for rep in r.json()["reports"]}
        assert states["gouv.recherche-entreprises"] == "operationnel"
        assert states["gleif.lei"] == "operationnel"
        assert states["gouv.bodacc"] == "operationnel"
        assert states["web.url"] == "inconnu"  # pas de sonde par défaut

        r = await client.get("/api/v1/connectors/inconnu.x/health")
        assert r.status_code == 404


async def test_build_real_connectors_quatre_connecteurs_v12():
    connectors = build_real_connectors(fetch_fn=fake_fetch({}))
    assert [c.manifest.id for c in connectors] == ["gouv.recherche-entreprises", "gouv.bodacc", "gleif.lei", "web.url"]
    assert all(c.manifest.trust_level.value == "official" for c in connectors)
    assert all(c.manifest.last_checked for c in connectors)
