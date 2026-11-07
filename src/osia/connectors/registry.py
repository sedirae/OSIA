from __future__ import annotations

from .base import Connector, TrustLevel


class ConnectorRegistry:
    """Registre des connecteurs : activation/désactivation individuelle (FONCTIONNEL §6).

    Niveau de confiance dans le manifeste (T5.1) ; seuls les connecteurs activés sont autorisés
    par le PolicyEngine. Les connecteurs EXPERIMENTAL sont désactivés par défaut et exigent une
    autorisation explicite (T5.1)."""

    def __init__(self):
        self._connectors: dict[str, Connector] = {}
        self._enabled: set[str] = set()

    def register(self, connector: Connector, *, enabled: bool | None = None) -> None:
        self._connectors[connector.manifest.id] = connector
        if enabled is None:
            enabled = connector.manifest.trust_level != TrustLevel.EXPERIMENTAL
        if enabled:
            self._enabled.add(connector.manifest.id)

    def set_enabled(self, connector_id: str, enabled: bool) -> None:
        if connector_id not in self._connectors:
            raise KeyError(f"connecteur inconnu: {connector_id}")
        if enabled:
            self._enabled.add(connector_id)
        else:
            self._enabled.discard(connector_id)

    def get(self, connector_id: str) -> Connector | None:
        if connector_id in self._enabled:
            return self._connectors.get(connector_id)
        return None

    def authorized_ids(self) -> set[str]:
        return set(self._enabled)

    def list(self) -> list[dict]:
        return [
            {
                "id": c.manifest.id,
                "version": c.manifest.version,
                "trust_level": c.manifest.trust_level.value,
                "capabilities": c.manifest.capabilities,
                "domains": c.manifest.domains,
                "paid": c.manifest.paid,
                "enabled": c.manifest.id in self._enabled,
            }
            for c in self._connectors.values()
        ]
