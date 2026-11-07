from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

import aiohttp

from ..netguard import NetworkGuard
from .base import Connector, ConnectorManifest, FetchRequest, FetchResult, Provenance

# Contrat d'un fetch brut : UNE requête sans suivre les redirections -> (status, headers, body).
# Le NetworkGuard gère les redirections, le rate limit et l'anti-SSRF (T5.4).
FetchFn = Callable[[str], Awaitable[tuple[int, dict, bytes]]]


async def aiohttp_fetch(url: str) -> tuple[int, dict, bytes]:
    """Fetch réel par aiohttp, sans suivre les redirections (gérées par le guard)."""
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "osia/0.1 (+investigation-osint)"}) as session:
        async with session.get(url, allow_redirects=False) as resp:
            body = await resp.read()
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body


class HttpConnector(Connector):
    """Connecteur HTTP de base (B3) : toute requête sortante passe par le NetworkGuard (T5.4).

    `fetch_fn` est injectable pour les tests hors ligne (fixtures, AGENTS.md : connecteurs
    simulés en CI, aucun appel externe facturable sans enveloppe autorisée)."""

    def __init__(
        self,
        manifest: ConnectorManifest,
        netguard: Optional[NetworkGuard] = None,
        fetch_fn: Optional[FetchFn] = None,
        probe_query: Optional[str] = None,
    ):
        self.manifest = manifest
        self.netguard = netguard
        self.fetch_fn = fetch_fn or aiohttp_fetch
        # Sonde légère utilisée par le contrôle de santé (B7 §9.5) ; None = sonde manuelle requise.
        self.probe_query = probe_query

    async def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> tuple[int, dict, bytes]:
        if params:
            from urllib.parse import urlencode

            sep = "&" if "?" in url else "?"
            url = url + sep + urlencode(params)
        if self.netguard is not None:
            return await self.netguard.guarded_request(self.fetch_fn, url)
        return await self.fetch_fn(url)

    def _result(self, *, query: str, url: str, status: int, payload: Any, media_type: str = "application/json", extracted_text: Optional[str] = None) -> FetchResult:
        content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return FetchResult(
            content=content,
            provenance=Provenance(source_id=self.manifest.id, url=url, http_status=status),
            media_type=media_type,
            extracted_text=extracted_text if extracted_text is not None else content,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raise NotImplementedError

    def validate_response(self, payload: Any) -> list[str]:
        """Contrôle sémantique (B7 §9.1) : retourne la liste des problèmes de structure.
        Une réponse HTTP 200 ne suffit pas à prouver la validité fonctionnelle."""
        return []
