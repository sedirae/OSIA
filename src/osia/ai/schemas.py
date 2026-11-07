from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceSelection(BaseModel):
    """Proposition typée d'une requête source (audit F05) : connecteur retenu + requête + params."""

    connector_id: str
    query: str
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None


class PlanProposal(BaseModel):
    """Sortie structurée du rôle 'planning' (T8.2/T8.6).

    `selections` (typées, F05) est préféré à `source_queries` (hérité) quand présent : le backend
    valide chaque `connector_id` contre le registre des connecteurs actifs."""

    sub_objectives: list[str] = Field(default_factory=list)
    source_queries: list[str] = Field(default_factory=list)
    selections: list[SourceSelection] = Field(default_factory=list)
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
    """Sortie structurée du rôle 'synthesis'.

    `decisive_proof_ids` (F06) référence des identifiants STABLES de preuves (champ `id` du
    contexte fourni) — préféré à l'égalité d'URL `decisive_sources`, conservée en repli."""

    conclusion: str
    support: str = Field(description="documenté | corroboré | à confirmer | contradictoire | non établi")
    decisive_sources: list[str] = Field(default_factory=list)
    decisive_proof_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    objective_sufficiently_supported: bool = False
    suggested_followups: list[str] = Field(default_factory=list)
