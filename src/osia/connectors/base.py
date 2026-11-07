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
    id: str
    version: str
    trust_level: TrustLevel = TrustLevel.OFFICIAL
    capabilities: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    paid: bool = False
    cost_per_call_cents: Optional[int] = None
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
