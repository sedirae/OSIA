from __future__ import annotations

import json

from .base import Connector, ConnectorManifest, FetchRequest, FetchResult, Provenance


class SimulatedConnector(Connector):
    """Connecteur simulé pour tests hors ligne (T3.14, AGENTS.md) : aucune dépense, réponses déterministes."""

    def __init__(self, connector_id: str = "simulated.web", fixtures: dict[str, dict] | None = None):
        self.manifest = ConnectorManifest(
            id=connector_id,
            version="0.1.0",
            capabilities=["web_fetch"],
            domains=["example.test"],
            paid=False,
        )
        self.fixtures = fixtures or {}
        self.calls: list[str] = []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request.query)
        fixture = self.fixtures.get(request.query)
        if fixture is None:
            fixture = {"query": request.query, "results": [], "note": "aucun résultat simulé"}
        content = json.dumps(fixture, ensure_ascii=False)
        return FetchResult(
            content=content,
            provenance=Provenance(
                source_id=self.manifest.id,
                url=f"https://{self.manifest.domains[0]}/simulated?q={request.query}",
                http_status=200,
            ),
            media_type="application/json",
            extracted_text=content,
        )
