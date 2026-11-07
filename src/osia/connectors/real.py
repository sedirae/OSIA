from __future__ import annotations

import json
import os
import sys
from html.parser import HTMLParser
from typing import Any

from ..security.isolation import run_isolated, run_isolated_sync
from .base import ConnectorManifest, FetchRequest, FetchResult, TrustLevel
from .http import HttpConnector, build_url


class _TextExtractor(HTMLParser):
    """Extraction texte d'un HTML (B3 : extraction web standard) — jamais d'exécution de script."""

    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def extract_text_from_html(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def extract_text_from_pdf(data: bytes) -> str:
    """Extraction texte d'un PDF textuel (B3, V1.2) en sous-processus isolé (rlimits, T5.2) :
    le parsing PDF n'a jamais lieu dans le processus du moteur (audit issue #17 F02)."""
    proc = run_isolated_sync([sys.executable, "-m", "osia.security.pdftool"], stdin_data=data)
    if proc.returncode != 0:
        raise ValueError("extraction PDF isolée échouée (document illisible ou limite atteinte)")
    return proc.stdout.decode("utf-8", errors="replace")


async def extract_text_from_pdf_isolated(data: bytes) -> str:
    """Variante async (chemin produit) : même isolation, sans bloquer la boucle d'événements."""
    rc, out, _err = await run_isolated([sys.executable, "-m", "osia.security.pdftool"], stdin_data=data)
    if rc != 0:
        raise ValueError("extraction PDF isolée échouée (document illisible ou limite atteinte)")
    return out.decode("utf-8", errors="replace")


def _gleif_record(rec: Any) -> dict:
    """Normalise un enregistrement LEI en tolérant les champs absents ou null (B7 §9.1 :
    une réponse mal formée doit produire un problème de structure, pas un crash)."""
    rec = rec if isinstance(rec, dict) else {}
    entity = ((rec.get("attributes") or {}).get("entity")) or {}
    return {
        "lei": rec.get("id"),
        "legal_name": (entity.get("legalName") or {}).get("value"),
        "country": (entity.get("legalAddress") or {}).get("country"),
    }


class RechercheEntreprisesConnector(HttpConnector):
    """API Recherche d'Entreprises (DINUM/api.gouv.fr) — V1.2, gratuite, sans jeton.

    Endpoint : https://recherche-entreprises.api.gouv.fr/search?q=<nom ou SIREN>
    Réponse : {results: [{siren, nom_complet, etat_administratif, nature_juridique,
    activite_principale, ...}], total_results, page, per_page}."""

    def __init__(self, **kw):
        super().__init__(
            ConnectorManifest(
                id="gouv.recherche-entreprises",
                version="1.0.0",
                trust_level=TrustLevel.OFFICIAL,
                provider="DINUM — api.gouv.fr",
                scope="France — entreprises et établissements (SIREN/SIRET)",
                categories=["entreprises", "établissements", "dirigeants (via fiche)"],
                capabilities=["search_company_by_name_or_siren"],
                access_methods=["api_ouverte_https"],
                auth="none",
                domains=["recherche-entreprises.api.gouv.fr"],
                paid=False,
                quotas="rate limit côté serveur (ordre de grandeur 2000 req/min/IP) — vérifier à l'intégration",
                conditions_url="https://recherche-entreprises.api.gouv.fr/docs/",
                last_checked="2026-11-07",
            ),
            probe_query="EDF",
            **kw,
        )
        self.base_url = os.environ.get("OSIA_RECHERCHE_ENTREPRISES_API_BASE", "https://recherche-entreprises.api.gouv.fr/search")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        params = {"q": request.query, "per_page": 5}
        url = build_url(self.base_url, params)
        status, _, body = await self._get(self.base_url, params=params)
        payload = json.loads(body.decode("utf-8"))
        results = payload.get("results") or []
        total = payload.get("total_results")
        if total is None:
            total = len(results)
        normalized = {
            "query": request.query,
            "total_results": total,
            "results": [
                {
                    "siren": (r or {}).get("siren"),
                    "nom_complet": (r or {}).get("nom_complet"),
                    "etat_administratif": (r or {}).get("etat_administratif"),
                    "nature_juridique": (r or {}).get("nature_juridique"),
                    "activite_principale": (r or {}).get("activite_principale"),
                    "adresse": ((r or {}).get("siege") or {}).get("adresse"),
                }
                for r in results
            ],
        }
        return self._result(query=request.query, url=url, status=status, payload=normalized)

    def validate_response(self, payload: Any) -> list[str]:
        """Contrôle sémantique de la réponse NORMALISÉE (B7 §9.1)."""
        problems = []
        if not isinstance(payload, dict) or "results" not in payload:
            return ["champ 'results' absent"]
        for i, r in enumerate(payload.get("results", [])):
            if not isinstance(r, dict) or not r.get("siren"):
                problems.append(f"results[{i}] sans 'siren'")
        return problems


class BodaccConnector(HttpConnector):
    """API BODACC (DILA) — annonces officielles, V1.2, gratuite.

    L'URL exacte de l'API DILA est configurable (OSIA_BODACC_API_BASE) et à confirmer à
    l'intégration (B2 §4.2 : disponibilité et conditions vérifiées au moment de l'intégration)."""

    def __init__(self, **kw):
        super().__init__(
            ConnectorManifest(
                id="gouv.bodacc",
                version="1.0.0",
                trust_level=TrustLevel.OFFICIAL,
                provider="DILA — BODACC (Bulletin officiel des annonces civiles et commerciales)",
                scope="France — annonces légales des entreprises (procédures collectives, actes RCS)",
                categories=["annonces légales", "procédures collectives", "événements d'entreprise"],
                capabilities=["search_bodacc_annonces"],
                access_methods=["api_ouverte_https"],
                auth="none",
                domains=["bodacc.datagouv.fr", "echanges.dila.gouv.fr", "www.data.gouv.fr"],
                paid=False,
                quotas="à vérifier à l'intégration (fiche DILA/data.gouv.fr)",
                conditions_url="https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-civiles-et-commerciales-bodacc",
                last_checked="2026-11-07",
            ),
            probe_query="EDF",
            **kw,
        )
        self.base_url = os.environ.get("OSIA_BODACC_API_BASE", "https://bodacc.datagouv.fr/api/v1/annonces")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        params = {"q": request.query, "limit": 5}
        url = build_url(self.base_url, params)
        status, _, body = await self._get(self.base_url, params=params)
        payload = json.loads(body.decode("utf-8"))
        raw = payload.get("results")
        if raw is None:
            raw = payload.get("data")
        results = raw or []
        total = payload.get("total")
        if total is None:
            total = ((payload.get("meta") or {}).get("pagination") or {}).get("total")
        if total is None:
            total = len(results)
        normalized = {"query": request.query, "total": total, "results": results}
        return self._result(query=request.query, url=url, status=status, payload=normalized)

    def validate_response(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict) or "results" not in payload:
            return ["champ 'results' absent dans la réponse normalisée"]
        return []


class GleifConnector(HttpConnector):
    """API GLEIF (LEI) — V1.2, gratuite, sans jeton.

    Endpoint : https://api.gleif.org/api/v1/lei-records?filter[lei]=<LEI> ou
    filter[entity.legalName]=<nom>. Réponse : {data: [{id: LEI, attributes: {...}}], meta}."""

    def __init__(self, **kw):
        super().__init__(
            ConnectorManifest(
                id="gleif.lei",
                version="1.0.0",
                trust_level=TrustLevel.OFFICIAL,
                provider="GLEIF — Global Legal Entity Identifier Foundation",
                scope="International — LEI et relations de parenté déclarées",
                categories=["entreprises internationales", "LEI", "relations de parenté"],
                capabilities=["search_lei_by_name_or_lei"],
                access_methods=["api_ouverte_https"],
                auth="none",
                domains=["api.gleif.org"],
                paid=False,
                quotas="rate limit GLEIF (ordre de grandeur 30 req/s) — vérifier à l'intégration",
                conditions_url="https://api.gleif.org/api/v1/lei-records",
                last_checked="2026-11-07",
            ),
            probe_query="ELECTRICITE DE FRANCE",
            **kw,
        )
        self.base_url = "https://api.gleif.org/api/v1/lei-records"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        q = request.query.strip()
        # LEI = 20 caractères alphanumériques ; sinon recherche par nom
        if len(q) == 20 and q.isalnum():
            params = {"filter[lei]": q}
        else:
            params = {"filter[entity.legalName]": q}
        params["page[size]"] = 5
        url = build_url(self.base_url, params)
        status, _, body = await self._get(self.base_url, params=params)
        payload = json.loads(body.decode("utf-8"))
        data = payload.get("data") or []
        normalized = {
            "query": q,
            "results": [_gleif_record(rec) for rec in data],
        }
        return self._result(query=q, url=url, status=status, payload=normalized)

    def validate_response(self, payload: Any) -> list[str]:
        """Contrôle sémantique de la réponse NORMALISÉE (B7 §9.1)."""
        if not isinstance(payload, dict) or "results" not in payload:
            return ["champ 'results' absent"]
        for i, rec in enumerate(payload.get("results", [])):
            if not isinstance(rec, dict) or not rec.get("lei"):
                return [f"results[{i}] sans 'lei'"]
        return []


class WebUrlConnector(HttpConnector):
    """Web par URL (V1.2) : lit une page publique fournie ou découverte, et ses PDF textuels.

    HTTP simple d'abord via le NetworkGuard (T5.4) ; Playwright isolé (T5.3) reste différé
    (nécessaire et autorisé). Aucun contournement de CAPTCHA/protection (T5.3)."""

    def __init__(self, **kw):
        super().__init__(
            ConnectorManifest(
                id="web.url",
                version="1.0.0",
                trust_level=TrustLevel.OFFICIAL,
                provider="OSIA — lecture directe de pages publiques fournies",
                scope="URL publiques fournies ou découvertes dans l'enquête",
                categories=["pages web", "PDF textuels"],
                capabilities=["fetch_public_url"],
                access_methods=["http_get", "extraction_html", "extraction_pdf_textuel"],
                auth="none",
                domains=[],  # toute URL fournie est soumise au NetworkGuard (allowlist/denylist + anti-SSRF)
                paid=False,
                quotas="rate limit 1 req/s/domaine, taille plafonnée (politique réseau)",
                conditions_url=None,
                last_checked="2026-11-07",
            ),
            **kw,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        url = request.query.strip()
        status, headers, body = await self._get(url)
        media = headers.get("content-type", "application/octet-stream").split(";")[0].strip().lower()
        if media == "application/pdf" or url.lower().endswith(".pdf"):
            text = await extract_text_from_pdf_isolated(body)
            return self._result(query=url, url=url, status=status, payload={"url": url, "media_type": "application/pdf", "text": text}, media_type="application/pdf", extracted_text=text)
        text = body.decode("utf-8", errors="replace")
        extracted = extract_text_from_html(text) if "html" in media else text
        return self._result(query=url, url=url, status=status, payload={"url": url, "media_type": media, "text": extracted}, media_type=media, extracted_text=extracted)

    def validate_response(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict) or "text" not in payload:
            return ["champ 'text' absent"]
        return []


def build_real_connectors(**kw) -> list[HttpConnector]:
    """Connecteurs V1.2 (PERIMETRE-V1 §V1.2) : recherche d'entreprises, BODACC, GLEIF, web par URL."""
    return [
        RechercheEntreprisesConnector(**kw),
        BodaccConnector(**kw),
        GleifConnector(**kw),
        WebUrlConnector(**kw),
    ]
