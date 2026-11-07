from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

import aiohttp

from ..netguard import NetworkGuard, RequestContext
from ..nethttp import DEFAULT_MAX_BYTES, DEFAULT_SESSION_POOL, pool_key, read_bounded
from .base import Connector, ConnectorManifest, FetchRequest, FetchResult, Provenance

# Contrat d'un fetch brut : UNE requête sans suivre les redirections -> (status, headers, body).
# Le NetworkGuard gère les redirections, le rate limit et l'anti-SSRF (T5.4).
FetchFn = Callable[[str], Awaitable[tuple[int, dict, bytes]]]


def build_url(url: str, params: Optional[dict[str, Any]] = None) -> str:
    """URL de requête avec paramètres encodés (urlencode). Utilisée pour l'appel ET la
    provenance : l'URL stockée avec la preuve reste bien formée même si la requête
    contient des caractères réservés (T5.6)."""
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urlencode(params)
    return url


async def aiohttp_fetch(url: str, ctx: Optional[RequestContext] = None) -> tuple[int, dict, bytes]:
    """Fetch réel par aiohttp, sans suivre les redirections (gérées par le guard).

    Accepte un `ctx` (accepts_ctx, F02) : les IPs validées par le guard sont épinglées au
    transport (anti-TOCTOU DNS) et la réponse est lue en streaming borné à `ctx.max_bytes`."""
    timeout = aiohttp.ClientTimeout(total=15)
    pinned = ctx.pinned if ctx is not None else None
    max_bytes = ctx.max_bytes if ctx is not None else DEFAULT_MAX_BYTES
    # Réserve audit PR#18 : session réutilisée via le pool (clé = host+IPs épinglées,
    # audit PR#24 P3-c) au lieu d'une ClientSession + TCPConnector par requête.
    key = pool_key(pinned)
    session = await DEFAULT_SESSION_POOL.session(
        key, pinned=pinned, timeout=timeout, headers={"User-Agent": "osia/0.1 (+investigation-osint)"}
    )
    async with session.get(url, allow_redirects=False) as resp:
        body = await read_bounded(resp, max_bytes, resp.url.host or "")
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body


aiohttp_fetch.accepts_ctx = True  # le guard lui transmet pinned/max_bytes/same_origin (F02)


class HttpStatusError(Exception):
    """Statut HTTP >= 400 (audit F13, T5.6) : une erreur HTTP (404/429/500…) n'est PAS un
    résultat vide — elle est levée, jamais transformée en FetchResult « sans contenu »."""

    def __init__(self, status: int, url: str):
        super().__init__(f"http_status:{status} {url}")
        self.status = status
        self.url = url


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
        full_url = build_url(url, params)
        if self.netguard is not None:
            status, headers, body = await self.netguard.guarded_request(self.fetch_fn, full_url)
        else:
            status, headers, body = await self.fetch_fn(full_url)
        if status >= 400:
            # F13 : 404/429/500… = erreur, distincte d'un résultat vide (jamais un FetchResult)
            raise HttpStatusError(status, full_url)
        return status, headers, body

    def _result(self, *, query: str, url: str, status: int, payload: Any, media_type: str = "application/json", extracted_text: Optional[str] = None, raw: Optional[bytes] = None) -> FetchResult:
        content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return FetchResult(
            content=content,
            provenance=Provenance(source_id=self.manifest.id, url=url, http_status=status),
            media_type=media_type,
            extracted_text=extracted_text if extracted_text is not None else content,
            raw_bytes=raw,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raise NotImplementedError
