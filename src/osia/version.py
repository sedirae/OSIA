"""EXEC-06 — mises à jour manuelles avec notification.

La mise à jour reste MANUELLE (l'utilisateur installe la nouvelle version) ; OSIA fournit
la NOTIFICATION : une vérification best-effort de la dernière version publiée, au démarrage
du serveur, via `osia version --check`, et via `GET /api/v1/system/version`.

Le check passe par le NetworkGuard (allowlist pypi.org, lecture bornée, timeout court) :
aucun échec réseau ne doit jamais empêcher le démarrage — toute erreur retourne None.
Aucun appel n'est effectué en dehors de ces points explicites (hors ligne par défaut en
test : `fetch_fn` injectable).
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional

from .netguard import NetworkGuard, NetworkPolicy

__version__ = "0.1.0"

DEFAULT_CHECK_URL = "https://pypi.org/pypi/osia/json"
CHECK_TIMEOUT_SECONDS = 5.0

# Contrat d'un fetch brut injectable en test : (url, ctx) -> (status, headers, body).
FetchFn = Callable[..., Awaitable[tuple[int, dict, bytes]]]


def _version_guard() -> NetworkGuard:
    return NetworkGuard(
        NetworkPolicy(
            allowed_domains={"pypi.org"},
            min_interval_seconds=0,
            max_bytes=1024 * 1024,
            timeout_seconds=CHECK_TIMEOUT_SECONDS,
        )
    )


async def fetch_latest_version(
    url: str = DEFAULT_CHECK_URL,
    fetch_fn: Optional[FetchFn] = None,
) -> Optional[str]:
    """Retourne la dernière version publiée (PyPI) ou None si indisponible.

    Ne lève JAMAIS : réseau coupé, JSON invalide, statut >= 400 -> None."""
    if fetch_fn is None:
        from .connectors.http import aiohttp_fetch

        fetch_fn = aiohttp_fetch
    try:
        status, _headers, body = await _version_guard().guarded_request(fetch_fn, url)
        if status != 200:
            return None
        data = json.loads(body.decode("utf-8"))
        version = data.get("info", {}).get("version")
        return version if isinstance(version, str) and version else None
    except Exception:
        return None


def is_newer(latest: Optional[str], current: str = __version__) -> bool:
    """Comparaison de versions sémantiques simples (x.y.z) — False si latest inconnu."""
    if not latest:
        return False

    def parts(v: str) -> tuple:
        out = []
        for p in v.split("."):
            num = ""
            for ch in p:
                if ch.isdigit():
                    num += ch
                else:
                    break
            out.append(int(num) if num else 0)
        return tuple(out)

    try:
        return parts(latest) > parts(current)
    except Exception:
        return False
