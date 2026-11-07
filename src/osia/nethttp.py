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


def pool_key(pinned: Optional[PinnedTarget], fallback: str = "default") -> str:
    """Clé de pool : inclut le statut épinglé ET les IPs validées (audit PR#24 P3-c) —
    une session créée sans pin ne doit jamais être réutilisée pour un appel épinglé
    (le pin serait perdu, anti-TOCTOU affaibli), et un changement d'IPs validées pour un
    même host doit ouvrir une nouvelle session."""
    if pinned is None:
        return fallback
    return f"pinned:{pinned.host}:{','.join(pinned.ips)}"


class SessionPool:
    """Pool de sessions aiohttp réutilisées entre requêtes (réserve audit PR#18 :
    auparavant une ClientSession + un TCPConnector étaient créés PAR requête).

    Une session épinglée (PinnedResolver) ne peut servir que son host ET ses IPs : la clé
    du pool est donc `pool_key(pinned)` (ou "default"). Les sessions sont fermées via
    `close()`."""

    def __init__(self) -> None:
        import asyncio

        self._sessions: dict[str, aiohttp.ClientSession] = {}
        self._lock = asyncio.Lock()

    async def session(
        self,
        key: str,
        *,
        pinned: Optional[PinnedTarget] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        headers: Optional[dict] = None,
    ) -> aiohttp.ClientSession:
        async with self._lock:
            s = self._sessions.get(key)
            if s is None or s.closed:
                s = aiohttp.ClientSession(
                    timeout=timeout or aiohttp.ClientTimeout(total=15),
                    connector=make_connector(pinned),
                    headers=headers or {},
                )
                self._sessions[key] = s
            return s

    async def close(self) -> None:
        async with self._lock:
            for s in self._sessions.values():
                if not s.closed:
                    await s.close()
            self._sessions.clear()


# Pool process-wide utilisé par les fetch réels (aiohttp_fetch, appels IA) ; les tests
# hors ligne injectent des fetch_fn simulés et ne l'utilisent jamais.
DEFAULT_SESSION_POOL = SessionPool()


async def close_default_session_pool() -> None:
    await DEFAULT_SESSION_POOL.close()


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
