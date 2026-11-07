from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


class NetworkDeny(Exception):
    """Refus réseau par la politique centralisée (T5.4) : raison explicite, jamais d'URL complète
    journalisée (les query strings peuvent contenir des secrets)."""

    def __init__(self, reason: str, host: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.host = host


# Réseaux jamais joignables depuis un connecteur (T5.4 anti-SSRF : interne/local non autorisés).
DEFAULT_BLOCKED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15",
        "224.0.0.0/4", "240.0.0.0/4",
        "::1/128", "::/128", "fc00::/7", "fe80::/10", "ff00::/8",
    )
]

_ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class NetworkPolicy:
    """Politique centralisée des accès réseau (T5.4), indépendante des connecteurs."""

    allowed_domains: set[str] = field(default_factory=set)  # vide = tous les domaines non bloqués
    denied_domains: set[str] = field(default_factory=set)
    blocked_networks: list = field(default_factory=lambda: list(DEFAULT_BLOCKED_NETWORKS))
    max_redirects: int = 3
    timeout_seconds: float = 15.0
    max_bytes: int = 10 * 1024 * 1024  # 10 Mo par réponse (V1.4 : 15 s / requête HTTP)
    min_interval_seconds: float = 1.0  # rate limit par domaine

    def domain_allowed(self, host: str) -> bool:
        h = host.lower().rstrip(".")
        if any(h == d or h.endswith("." + d) for d in self.denied_domains):
            return False
        if self.allowed_domains:
            return any(h == d or h.endswith("." + d) for d in self.allowed_domains)
        return True

    def ip_blocked(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(ip in net for net in self.blocked_networks)


Resolver = Callable[[str, int], Awaitable[list[tuple]]]


@dataclass
class PinnedTarget:
    """Adresses validées par `resolve_and_check`, à épingler au transport HTTP (anti-TOCTOU DNS :
    le transport ne résout plus le nom, il se connecte aux seules IPs contrôlées, F02)."""

    host: str
    port: int
    ips: list[str]


@dataclass
class RequestContext:
    """Contexte transmis au fetch quand il déclare `accepts_ctx = True` (F02) :

    - `pinned` : IPs validées à utiliser pour la connexion (SNI/Host conservés) ;
    - `max_bytes` : plafond de lecture streamée de la réponse (y compris décompressée) ;
    - `same_origin` : False sur redirection inter-origines -> le fetch doit supprimer les
      credentials (Authorization, Cookie) de sa requête (T8.8)."""

    pinned: Optional[PinnedTarget]
    max_bytes: int
    same_origin: bool


class NetworkGuard:
    """Garde-fou réseau central (T5.4) : tout accès sortant des connecteurs passe par lui.

    - schéma http/https uniquement ; domaine dans la denylist ou hors allowlist -> refus ;
    - résolution DNS puis filtrage de CHAQUE IP résolue (anti-SSRF : interne/local bloqués) ;
    - redirections suivies manuellement, re-vérifiées à chaque saut, plafonnées ;
    - taille de réponse plafonnée, timeout, rate limit par domaine ;
    - blocages journalisés dans l'audit de sécurité (T5.9), sans l'URL complète.
    """

    def __init__(
        self,
        policy: NetworkPolicy,
        audit=None,
        resolver: Optional[Resolver] = None,
    ):
        self.policy = policy
        self.audit = audit
        self._resolver = resolver or self._default_resolver
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    async def _default_resolver(host: str, port: int) -> list[tuple]:
        loop = asyncio.get_running_loop()
        return await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)

    def _log_block(self, reason: str, host: str) -> None:
        if self.audit is not None:
            self.audit.log("net.blocked", "denied", detail={"reason": reason, "host": host})

    def check_url(self, url: str) -> str:
        """Valide une URL sans réseau : schéma, domaine. Retourne le host. Lève NetworkDeny."""
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            self._log_block("scheme_non_autorise", parsed.hostname or "")
            raise NetworkDeny("scheme_non_autorise", parsed.hostname or "")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            self._log_block("host_absent", "")
            raise NetworkDeny("host_absent")
        try:
            parsed.port
        except ValueError:
            self._log_block("port_invalide", host)
            raise NetworkDeny("port_invalide", host)
        # IP littérale : filtrage direct anti-SSRF contre les réseaux bloqués…
        try:
            ip = ipaddress.ip_address(host)
            if self.policy.ip_blocked(ip):
                self._log_block("ip_interne_bloquee", host)
                raise NetworkDeny("ip_interne_bloquee", host)
        except ValueError:
            pass
        # …puis allowlist/denylist appliquée aussi aux IP littérales :
        # sans cela, une IP publique littérale contournerait l'allowlist de domaines.
        if not self.policy.domain_allowed(host):
            self._log_block("domaine_non_autorise", host)
            raise NetworkDeny("domaine_non_autorise", host)
        return host

    async def resolve_and_check(self, host: str, port: int = 443) -> list[str]:
        """Résout le host et vérifie que CHAQUE IP résolue est joignable (anti-SSRF DNS)."""
        try:
            infos = await self._resolver(host, port)
        except OSError as exc:
            self._log_block("resolution_echouée", host)
            raise NetworkDeny("resolution_echouée", host) from exc
        ips: list[str] = []
        for info in infos:
            sockaddr = info[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if self.policy.ip_blocked(ip):
                self._log_block("ssrf_ip_bloquee", host)
                raise NetworkDeny("ssrf_ip_bloquee", host)
            ips.append(ip_str)
        if not ips:
            self._log_block("resolution_vide", host)
            raise NetworkDeny("resolution_vide", host)
        return ips

    async def _rate_limit(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last_call.get(host, 0.0)
            wait = self.policy.min_interval_seconds - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call[host] = time.monotonic()

    @staticmethod
    def _origin_of(url: str) -> tuple[str, str, int]:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port or (443 if scheme == "https" else 80)
        return scheme, host, port

    async def guarded_request(
        self,
        fetch: Callable[..., Awaitable[tuple[int, dict, bytes]]],
        url: str,
    ) -> tuple[int, dict, bytes]:
        """Exécute une requête HTTP via `fetch(url)` en appliquant la politique complète :
        check URL, résolution DNS anti-SSRF, rate limit, redirections re-vérifiées et plafonnées,
        taille plafonnée. `fetch` doit faire UNE requête sans suivre les redirections et retourner
        (status, headers, body).

        Si `fetch` déclare `accepts_ctx = True`, il reçoit en plus `ctx=RequestContext(...)` :
        les IPs validées à épingler au transport (le résultat de resolve_and_check n'est plus
        abandonné — F02), le plafond de lecture, et `same_origin=False` sur redirection
        inter-origines pour y supprimer les credentials."""
        original_origin = self._origin_of(url)
        current = url
        for _ in range(self.policy.max_redirects + 1):
            host = self.check_url(current)
            port = urllib.parse.urlsplit(current).port or (443 if current.startswith("https") else 80)
            ips = await self.resolve_and_check(host, port)
            await self._rate_limit(host)
            ctx = RequestContext(
                pinned=PinnedTarget(host=host, port=port, ips=ips),
                max_bytes=self.policy.max_bytes,
                same_origin=self._origin_of(current) == original_origin,
            )
            if getattr(fetch, "accepts_ctx", False):
                status, headers, body = await asyncio.wait_for(fetch(current, ctx=ctx), timeout=self.policy.timeout_seconds)
            else:
                status, headers, body = await asyncio.wait_for(fetch(current), timeout=self.policy.timeout_seconds)
            if len(body) > self.policy.max_bytes:
                self._log_block("taille_depassee", host)
                raise NetworkDeny("taille_depassee", host)
            if status in (301, 302, 303, 307, 308):
                location = headers.get("location") or headers.get("Location")
                if not location:
                    return status, headers, body
                current = urllib.parse.urljoin(current, location)
                continue
            return status, headers, body
        self._log_block("trop_de_redirections", host)
        raise NetworkDeny("trop_de_redirections", host)
