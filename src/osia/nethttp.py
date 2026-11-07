"""Transport HTTP aiohttp lié au contrôle NetworkGuard (T5.4, audit F02).

Ce module est le SEUL endroit où aiohttp établit une connexion : il reçoit les adresses
validées par `NetworkGuard.resolve_and_check` (via `RequestContext.pinned`) et les épingle au
transport via un resolver statique — le DNS n'est plus re-résolu entre le contrôle et la
connexion (anti-TOCTOU/rebinding), tout en conservant le nom d'hôte pour le SNI TLS et
l'en-tête Host. Les lectures de réponse sont bornées en streaming, y compris après
décompression, avant toute allocation complète.
"""

from __future__ import annotations

import socket
from typing import Optional

import aiohttp

from .netguard import NetworkDeny, PinnedTarget, RequestContext

# En-têtes d'authentification jamais transmis à une autre origine (redirection inter-origines).
CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "cookie"}

DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def drop_credential_headers(headers: dict, ctx: Optional[RequestContext]) -> dict:
    """Copie des headers sans credentials si la requête courante est inter-origines (F02, T8.8)."""
    if ctx is None or ctx.same_origin:
        return dict(headers)
    return {k: v for k, v in headers.items() if k.lower() not in CREDENTIAL_HEADERS}


class PinnedResolver(aiohttp.abc.AbstractResolver):
    """Resolver aiohttp épinglé : ne retourne QUE les IPs validées par le NetworkGuard.

    aiohttp connecte alors à ces IPs (`host`) tout en utilisant le nom d'origine (`hostname`)
    pour le SNI TLS et l'en-tête Host. Toute demande de résolution d'un autre nom est refusée."""

    def __init__(self, pinned: PinnedTarget):
        self._pinned = pinned

    async def resolve(self, host: str, port: int = 443, family: int = socket.AF_UNSPEC) -> list[dict]:
        if host.lower().rstrip(".") != self._pinned.host.lower().rstrip("."):
            raise NetworkDeny("host_non_epingle", host)
        out: list[dict] = []
        for ip in self._pinned.ips:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append({"hostname": host, "host": ip, "port": port, "family": fam, "proto": 0, "flags": 0})
        return out

    async def close(self) -> None:
        return None


def make_connector(pinned: Optional[PinnedTarget]) -> aiohttp.TCPConnector:
    """Connecteur aiohttp ; épinglé sur les IPs validées si `pinned` est fourni."""
    if pinned is not None:
        return aiohttp.TCPConnector(resolver=PinnedResolver(pinned))
    return aiohttp.TCPConnector()


async def read_bounded(resp: aiohttp.ClientResponse, max_bytes: int, host: str = "") -> bytes:
    """Lecture streamée bornée d'une réponse : Content-Length vérifié d'abord, puis lecture par
    blocs de 64 Ko en n'allouant jamais plus de max_bytes (la décompression est incluse, F02)."""
    content_length = resp.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise NetworkDeny("taille_depassee", host)
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await resp.content.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise NetworkDeny("taille_depassee", host)
        chunks.append(chunk)
    return b"".join(chunks)
