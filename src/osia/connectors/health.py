from __future__ import annotations

import enum
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ..netguard import NetworkDeny
from .base import Connector, FetchRequest
from .registry import ConnectorRegistry


class HealthState(str, enum.Enum):
    """États fonctionnels d'un connecteur (B7 §9.1)."""

    OPERATIONNEL = "operationnel"  # contrôles satisfaisants
    DEGRADE = "degrade"  # certaines fonctions utilisables, les autres exclues
    SUSPENDU = "suspendu"  # anomalie critique, restriction ou doute bloquant
    OBSOLETE = "obsolete"  # évolution ou remplacement exigeant adaptation
    INCONNU = "inconnu"  # aucun contrôle effectué / aucune sonde disponible


class HealthReport(BaseModel):
    connector_id: str
    state: HealthState
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = ""
    http_status: Optional[int] = None
    validation_problems: list[str] = Field(default_factory=list)
    probe_url: Optional[str] = None


class ConnectorHealthChecker:
    """Surveillance des connecteurs (B7 §9.1, CON-07/CON-08).

    V1 : contrôles déclenchés manuellement (API), aucun sondage planifié — la fréquence
    des vérifications périodiques relève du calendrier de maintenance avancée (B7 §9.5).
    Chaque contrôle combine une sonde légère et la validation sémantique de la réponse :
    une HTTP 200 ne suffit pas à prouver la validité fonctionnelle (B7 §9.1)."""

    def __init__(self, registry: ConnectorRegistry, *, stale_after_days: int = 180):
        self.registry = registry
        self.stale_after_days = stale_after_days
        self._reports: dict[str, HealthReport] = {}

    def last_report(self, connector_id: str) -> Optional[HealthReport]:
        return self._reports.get(connector_id)

    def all_reports(self) -> dict[str, HealthReport]:
        return dict(self._reports)

    async def check(self, connector_id: str, probe_query: Optional[str] = None) -> HealthReport:
        """Contrôle un connecteur. Un connecteur inconnu ou désactivé est SUSPENDU : il est
        retiré des recherches sans arrêter les autres sources (B7 §9.3, B-ACC-01/12)."""
        connector = self.registry.get(connector_id)
        if connector is None:
            report = HealthReport(
                connector_id=connector_id,
                state=HealthState.SUSPENDU,
                detail="connecteur inconnu ou désactivé : retiré des recherches sans bloquer les autres (B-ACC-01)",
            )
        else:
            report = await self._check_connector(connector, probe_query)
        self._reports[connector_id] = report
        return report

    async def check_all(self, probe_query: Optional[str] = None) -> list[HealthReport]:
        return [await self.check(entry["id"], probe_query) for entry in self.registry.list()]

    async def _check_connector(self, connector: Connector, probe_query: Optional[str]) -> HealthReport:
        cid = connector.manifest.id
        obsolete = self._obsolescence(connector)
        if obsolete is not None:
            return obsolete
        query = probe_query if probe_query is not None else getattr(connector, "probe_query", None)
        if not query:
            return HealthReport(
                connector_id=cid,
                state=HealthState.INCONNU,
                detail="aucune sonde par défaut pour ce connecteur : contrôle manuel avec une requête explicite requis (B7 §9.5)",
            )
        try:
            result = await connector.fetch(FetchRequest(query=query))
        except NetworkDeny as exc:
            return HealthReport(
                connector_id=cid,
                state=HealthState.SUSPENDU,
                detail=f"sonde refusée par le NetworkGuard (restriction bloquante, T5.4) : {exc.reason}",
                probe_url=query,
            )
        except Exception as exc:  # sonde indisponible : timeout, DNS, connexion refusée...
            return HealthReport(
                connector_id=cid,
                state=HealthState.SUSPENDU,
                detail=f"sonde indisponible : {type(exc).__name__} : {exc}",
                probe_url=query,
            )
        status = result.provenance.http_status
        try:
            payload = json.loads(result.content)
        except (json.JSONDecodeError, TypeError):
            payload = result.content
        problems = connector.validate_response(payload)
        if status is not None and 200 <= status < 300 and not problems:
            return HealthReport(
                connector_id=cid,
                state=HealthState.OPERATIONNEL,
                detail="sonde satisfaisante, structure de réponse conforme",
                http_status=status,
                probe_url=result.provenance.url,
            )
        if status in (401, 403):
            return HealthReport(
                connector_id=cid,
                state=HealthState.SUSPENDU,
                detail=f"authentification refusée par la source (HTTP {status}) : restriction bloquante, suspension jusqu'à vérification (B7 §9.4)",
                http_status=status,
                validation_problems=problems,
                probe_url=result.provenance.url,
            )
        return HealthReport(
            connector_id=cid,
            state=HealthState.DEGRADE,
            detail=f"réponse reçue (HTTP {status}) mais validation sémantique incomplète : certaines fonctions restent utilisables, les autres sont exclues (B7 §9.1)",
            http_status=status,
            validation_problems=problems,
            probe_url=result.provenance.url,
        )

    def _obsolescence(self, connector: Connector) -> Optional[HealthReport]:
        """Obsolète : conditions d'accès non revérifiées depuis trop longtemps (B7 §9.4 :
        chaque connecteur porte la date de vérification de ses conditions)."""
        cid = connector.manifest.id
        lc = connector.manifest.last_checked
        if not lc:
            return HealthReport(
                connector_id=cid,
                state=HealthState.OBSOLETE,
                detail="last_checked absent : conditions d'accès et de réutilisation non vérifiées (B7 §9.4)",
            )
        try:
            checked = datetime.fromisoformat(lc)
        except ValueError:
            return HealthReport(connector_id=cid, state=HealthState.OBSOLETE, detail=f"last_checked illisible : {lc!r}")
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - checked
        if age > timedelta(days=self.stale_after_days):
            return HealthReport(
                connector_id=cid,
                state=HealthState.OBSOLETE,
                detail=f"conditions vérifiées il y a {age.days} jours (>{self.stale_after_days}) : revérification requise avant utilisation (B7 §9.4)",
            )
        return None
