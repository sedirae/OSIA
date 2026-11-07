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


# Garde-fous V1.4 non surchargeables à la hausse : 2 opérations externes simultanées,
# 15 s max par requête HTTP, 60 s max par appel IA (PERIMETRE-V1 §V1.4, T4.8).
_TECH_GUARDS = ("max_concurrent_external_ops", "http_timeout_seconds", "ai_timeout_seconds")


def limits_from_profile_row(
    row: asyncpg.Record,
    overrides: Optional[dict[str, Any]] = None,
) -> LimitSet:
    """Limites effectives : plafonds du profil (table profiles, source de vérité) + garde-fous
    V1.4, puis overrides explicites de la requête CLAMÉS : un override ne peut jamais augmenter
    une limite au-delà du niveau supérieur (D3 §5.4 : une limite inférieure ne lève jamais un
    plafond supérieur ; D7 §9.2 ; T4.8 : les garde-fous ne sont pas désactivables par surcharge).
    Les valeurs hors bornes du schéma (LimitSet ge/le) sont rejetées par validation pydantic."""
    merged: dict[str, Any] = {field: row[field] for field in _PROFILE_FIELDS}
    for field in _TECH_GUARDS:
        merged[field] = LimitSet.model_fields[field].default
    if overrides:
        for key, value in overrides.items():
            if key in LimitSet.model_fields and value is not None:
                merged[key] = min(int(value), int(merged[key]))  # clamp : jamais au-dessus du profil
    return LimitSet(**merged)
