from __future__ import annotations

import json
from typing import Any

import asyncpg

from ..models import LimitSet


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def limits_from_record(row: asyncpg.Record) -> LimitSet:
    return LimitSet(**_loads(row["effective_limits"]))


def limits_from_json(data: dict[str, Any]) -> LimitSet:
    return LimitSet(**_loads(data))
