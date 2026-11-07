from __future__ import annotations

import json
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from .base import AIAdapter

T = TypeVar("T", bound=BaseModel)


class SimulatedAIAdapter(AIAdapter):
    """Adaptateur IA simulé (T3.14) : réponses déterministes et rejouables, sans dépense."""

    def __init__(self, provider: str = "simulated", model: str = "simulated-1", scripted: dict[str, Any] | None = None):
        self.provider = provider
        self.model = model
        self.paid = False
        self.cost_per_call_cents = None
        self.scripted = scripted or {}
        self.calls: list[dict[str, Any]] = []

    async def complete(self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]) -> T:
        self.calls.append({"role": role, "prompt": prompt, "input": input_data})
        payload = self.scripted.get(role)
        if isinstance(payload, list):
            payload = payload.pop(0) if payload else {}
        elif callable(payload):
            payload = payload(role, input_data)
        if payload is None:
            payload = {}
        return response_model.model_validate(payload)
