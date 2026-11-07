"""Sélection backend des connecteurs de source (audit #17 F05).

Le parcours automatique ne choisit plus `simulated.web` en dur : les propositions typées de
l'IA (`PlanProposal.selections`) sont validées contre le registre, et à défaut la sélection
se fait à partir des capacités enregistrées. Un connecteur explicitement demandé mais
indisponible (inconnu ou désactivé) produit une erreur de configuration explicite — jamais
un repli silencieux sur la simulation. Les connecteurs simulés ne sont retenus que s'ils
sont seuls actifs (mode démo/test), et ce choix est marqué `simulated: true` dans la tâche.
"""

from __future__ import annotations

from typing import Any

from ..models import PolicyDeny
from .registry import ConnectorRegistry

# Capacités de récupération générique (requête libre) et de lecture d'URL fournie.
GENERIC_FETCH_CAPABILITIES = {"web_fetch", "fetch_public_url"}
URL_FETCH_CAPABILITIES = {"fetch_public_url"}


def is_simulated(connector_id: str) -> bool:
    return connector_id.startswith("simulated.")


def select_connector_id(
    registry: ConnectorRegistry,
    query: str,
    *,
    requested_id: str | None = None,
) -> tuple[str, bool]:
    """Retourne (connector_id retenu, simulated).

    - `requested_id` explicite : doit être actif dans le registre, sinon PolicyDeny
      (connecteur_demande_indisponible si connu mais désactivé, connecteur_inconnu sinon).
    - Sinon : sélection par capacités parmi les connecteurs actifs, en préférant les
      connecteurs réels ; la simulation n'est retenue que si aucun connecteur réel n'est actif.
    """
    if requested_id:
        if registry.get(requested_id) is None:
            known = any(e["id"] == requested_id for e in registry.list())
            raise PolicyDeny(
                f"connecteur_demande_indisponible:{requested_id}" if known else f"connecteur_inconnu:{requested_id}",
                "source",
            )
        return requested_id, is_simulated(requested_id)
    entries = [e for e in registry.list() if e.get("enabled")]
    real = [e for e in entries if not is_simulated(e["id"])]
    pool: list[dict[str, Any]] = real or entries
    if not pool:
        raise PolicyDeny("aucun_connecteur_actif", "source")
    is_url = query.strip().lower().startswith(("http://", "https://"))
    wanted = URL_FETCH_CAPABILITIES if is_url else GENERIC_FETCH_CAPABILITIES
    for entry in pool:
        if any(cap in wanted for cap in entry.get("capabilities", [])):
            return entry["id"], is_simulated(entry["id"])
    entry = pool[0]
    return entry["id"], is_simulated(entry["id"])
