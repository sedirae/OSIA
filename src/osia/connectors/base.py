from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class TrustLevel(str, enum.Enum):
    OFFICIAL = "official"
    APPROVED = "approved"
    EXPERIMENTAL = "experimental"


class ConnectorManifest(BaseModel):
    """Manifeste complet d'un connecteur (B1 §3.2, B7 §9.4) : identité, fournisseur, périmètre,
    catégories de données, méthodes d'accès, authentification, contraintes/quotas/coûts,
    conditions d'utilisation et date de vérification."""

    id: str
    version: str
    trust_level: TrustLevel = TrustLevel.OFFICIAL
    provider: str = ""
    scope: str = ""  # périmètre géographique ou thématique
    categories: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    access_methods: list[str] = Field(default_factory=list)
    auth: str = "none"  # none | api_key | oauth | ...
    domains: list[str] = Field(default_factory=list)
    paid: bool = False
    cost_per_call_cents: Optional[int] = None
    quotas: str = ""
    conditions_url: Optional[str] = None
    last_checked: Optional[str] = None  # date de vérification des conditions (B7 §9.4)
    http_timeout_seconds: int = 15


class FetchRequest(BaseModel):
    query: str
    params: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    source_id: str
    url: Optional[str] = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    method: str = "GET"
    http_status: Optional[int] = None


class FetchResult(BaseModel):
    content: str
    provenance: Provenance
    media_type: str = "application/json"
    extracted_text: Optional[str] = None


class Connector(ABC):
    """Contrat commun des connecteurs (B1, CON-07). Toute exécution passe par le PolicyEngine (B4)."""

    manifest: ConnectorManifest

    @abstractmethod
    async def fetch(self, request: FetchRequest) -> FetchResult:
        ...

    def validate_response(self, payload: Any) -> list[str]:
        """Contrôle sémantique (B7 §9.1) : liste des problèmes de structure de la réponse.
        Une réponse HTTP 200 ne suffit pas à prouver la validité fonctionnelle."""
        return []
