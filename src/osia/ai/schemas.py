from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PlanProposal(BaseModel):
    """Sortie structurée du rôle 'planning' (T8.2/T8.6)."""

    sub_objectives: list[str] = Field(default_factory=list)
    source_queries: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ExtractedEntity(BaseModel):
    kind: str
    name: str
    identifiers: dict[str, str] = Field(default_factory=dict)


class ProposedRelation(BaseModel):
    src: str
    dst: str
    type: str
    status: str = "hypothesis"


class Extraction(BaseModel):
    """Sortie structurée du rôle 'extraction'."""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ProposedRelation] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)


class Synthesis(BaseModel):
    """Sortie structurée du rôle 'synthesis'."""

    conclusion: str
    support: str = Field(description="documenté | corroboré | à confirmer | contradictoire | non établi")
    decisive_sources: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    objective_sufficiently_supported: bool = False
    suggested_followups: list[str] = Field(default_factory=list)


class SourceSelection(BaseModel):
    connector_id: str
    query: str
    rationale: Optional[str] = None
