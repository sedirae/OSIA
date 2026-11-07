from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIAdapter(ABC):
    """Adaptateur fournisseur (T8.1). Aucun appel modèle ne passe hors du courtier."""

    provider: str
    model: str
    paid: bool = False
    cost_per_call_cents: int | None = None

    @abstractmethod
    async def complete(self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]) -> T:
        ...

    async def ping(self) -> dict:
        """Test de connexion explicite (D2 §4.2). Par défaut : adaptateur sans point de contrôle
        réseau (simulé). Aucun appel facturable n'est lancé par un ping (B6)."""
        return {"ok": True, "provider": self.provider, "model": self.model, "paid": self.paid, "models": [self.model]}
