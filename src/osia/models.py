from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

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


PROFILES_V1: dict[str, dict[str, Any]] = {
    "rapide": dict(max_rebonds=2, max_source_requests=12, max_ai_calls=4, max_duration_seconds=120, max_cost_cents=5),
    "standard": dict(max_rebonds=4, max_source_requests=40, max_ai_calls=12, max_duration_seconds=600, max_cost_cents=20),
    "approfondi": dict(max_rebonds=8, max_source_requests=100, max_ai_calls=30, max_duration_seconds=1800, max_cost_cents=100),
}

DEFAULT_PROFILE = "rapide"


def resolve_limits(profile_id: str, overrides: Optional[dict[str, Any]] = None) -> LimitSet:
    base = PROFILES_V1.get(profile_id)
    if base is None:
        raise ValueError(f"profil inconnu: {profile_id}")
    merged = dict(base)
    if overrides:
        for key, value in overrides.items():
            if key in LimitSet.model_fields:
                merged[key] = value
    return LimitSet(**merged)


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
