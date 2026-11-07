from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg

from ..models import LimitSet

_PROFILE_FIELDS = (
    "max_rebonds",
    "max_source_requests",
    "max_ai_calls",
    "max_duration_seconds",
    "max_cost_cents",
)


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def limits_from_record(row: asyncpg.Record) -> LimitSet:
    return LimitSet(**_loads(row["effective_limits"]))


def limits_from_json(data: dict[str, Any]) -> LimitSet:
    return LimitSet(**_loads(data))


def limits_from_profile_row(
    row: asyncpg.Record,
    overrides: Optional[dict[str, Any]] = None,
) -> LimitSet:
    """Limites effectives : plafonds du profil (table profiles, source de vérité)
    complétés des valeurs par défaut, puis overrides explicites de la requête."""
    merged: dict[str, Any] = {field: row[field] for field in _PROFILE_FIELDS}
    if overrides:
        for key, value in overrides.items():
            if key in LimitSet.model_fields:
                merged[key] = value
    return LimitSet(**merged)
