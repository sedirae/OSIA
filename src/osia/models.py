from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class InvestigationState(str, enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    SUSPENDED = "suspended"
    STOPPED = "stopped"
    ERROR = "error"


class StopReason(str, enum.Enum):
    OBJECTIVE = "objective_suffisamment_etaye"
    DEPTH_LIMIT = "depth_limit"
    BUDGET = "budget_exhausted"
    SOURCES = "sources_exhausted"
    USER = "user_interrupt"
    TECHNICAL = "technical_error"
    SECURITY = "security_block"


class TaskState(str, enum.Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class OpKind(str, enum.Enum):
    SOURCE_REQUEST = "source_request"
    AI_CALL = "ai_call"


class OpState(str, enum.Enum):
    PLANNED = "planned"
    AUTHORIZED = "authorized"
    RESERVED = "reserved"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    UNCERTAIN = "uncertain"
    RECONCILED = "reconciled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReservationState(str, enum.Enum):
    RESERVED = "reserved"
    CONSUMED = "consumed"
    RELEASED = "released"


class LimitSet(BaseModel):
    max_rebonds: int = Field(ge=1, le=10)
    max_source_requests: int = Field(ge=0)
    max_ai_calls: int = Field(ge=0)
    max_duration_seconds: int = Field(gt=0)
    max_cost_cents: int = Field(ge=0)
    max_concurrent_external_ops: int = Field(default=2, ge=1)
    http_timeout_seconds: int = Field(default=15, gt=0)
    ai_timeout_seconds: int = Field(default=60, gt=0)


DEFAULT_PROFILE = "rapide"


class CreateInvestigationRequest(BaseModel):
    title: str = Field(min_length=1)
    objective: Optional[str] = None
    hints: list[str] = Field(default_factory=list)
    profile_id: str = DEFAULT_PROFILE
    limits: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None


class CreateBranchRequest(BaseModel):
    objective: str = Field(min_length=1)
    parent_branch_id: Optional[str] = None
    limits: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    explicit_acceptance: bool = False


class StopRequest(BaseModel):
    reason: StopReason = StopReason.USER


class Event(BaseModel):
    id: int
    investigation_id: Optional[str]
    branch_id: Optional[str]
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BudgetView(BaseModel):
    estimated_cents: int
    reserved_cents: int
    consumed_cents: int
    available_cents: int
    caps: dict[str, int]


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class PolicyDeny(Exception):
    def __init__(self, reason: str, scope: str = "policy"):
        super().__init__(reason)
        self.reason = reason
        self.scope = scope


class SupportLevel(str, enum.Enum):
    """Statut d'etayage documentaire (C6) : distinct de la decision humaine (T6.7, CON-10)."""

    DOCUMENTE = "documente"
    CORROBORE = "corrobore"
    A_CONFIRMER = "a_confirmer"
    CONTRADICTOIRE = "contradictoire"
    NON_ETABLI = "non_etabli"


class HumanDecision(str, enum.Enum):
    UNEXAMINED = "unexamined"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ClaimNature(str, enum.Enum):
    """Natures T6.7 : fait etabli, information rapportee, indice, hypothese, conclusion analytique."""

    FAIT_ETABLI = "fait_etabli"
    INFORMATION_RAPPORTEE = "information_rapportee"
    INDICE = "indice"
    HYPOTHESE = "hypothese"
    CONCLUSION_ANALYTIQUE = "conclusion_analytique"


class ConfidenceLevel(str, enum.Enum):
    HAUTE = "haute"
    MOYENNE = "moyenne"
    FAIBLE = "faible"
    INCONNUE = "inconnue"


CONFIDENCE_DIMENSIONS = (
    "fiabilite_source",
    "qualite_extraction",
    "solidite_preuves",
    "coherence_intersources",
    "fraicheur",
    "validation_humaine",
)


class MatchBasis(str, enum.Enum):
    EXACT_IDENTIFIER = "exact_identifier"
    SIMILARITY = "similarity"
    CROSS_REFERENCE = "cross_reference"


class MatchStatus(str, enum.Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    REJECTED = "rejected"


class DecisionAction(str, enum.Enum):
    VALIDATE = "validate"
    REJECT = "reject"
    CORRECT = "correct"
    ANNOTATE = "annotate"
    PROPOSE_MATCH = "propose_match"
    MERGE = "merge"
    UNDO = "undo"


class DecisionTargetType(str, enum.Enum):
    ENTITY = "entity"
    RELATION = "relation"
    ASSERTION = "assertion"
    MATCH_PROPOSAL = "match_proposal"


class DecisionRequest(BaseModel):
    """Action humaine supervisee sur le graphe (C6, CON-09) : historisee et reversible via `reverts`."""

    target_type: DecisionTargetType
    target_id: str
    action: DecisionAction
    payload: dict[str, Any] = Field(default_factory=dict)
    reverts: Optional[str] = None


class MatchProposalRequest(BaseModel):
    entity_a: str
    entity_b: str
    basis: MatchBasis = MatchBasis.SIMILARITY
    justification: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.FAIBLE


class ExportRequest(BaseModel):
    """Export d'une investigation (D5, T7.4) : archive .osia, rapport HTML autonome, ou les deux.

    La phrase secrete (chiffrement facultatif, CON-15) n'est jamais journalisee (OSIA-I-12)."""

    format: Literal["osia", "html", "both"] = "osia"
    branch_ids: Optional[list[str]] = None
    include_proofs: bool = True
    exclusions: list[str] = Field(default_factory=list)
    encrypt: bool = False
    passphrase: Optional[str] = None


class ImportPreviewRequest(BaseModel):
    """Previsualisation d'une archive .osia avant toute modification (T7.6)."""

    path: str
    passphrase: Optional[str] = None


class ImportApplyRequest(BaseModel):
    """Application supervisee d'un import (T7.6, D5.7.2) : aucun ecrasement silencieux,
    aucune reprise de recherche automatique."""

    path: str
    mode: Literal["add", "merge"] = "add"
    on_conflict: Literal["fail", "skip"] = "fail"
    passphrase: Optional[str] = None


class BackupCreateRequest(BaseModel):
    """Sauvegarde technique manuelle a chaud (T2.6, CON-16)."""

    dest_dir: Optional[str] = None
