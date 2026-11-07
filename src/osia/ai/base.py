from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIAdapter(ABC):
    """Adaptateur fournisseur (T8.1). Aucun appel modèle ne passe hors du courtier."""

    provider: str
    model: str
    paid: bool = False
    cost_per_call_cents: int | None = None
    max_output_tokens: Optional[int] = None  # plafond de tokens de sortie (borne, audit F03)

    @abstractmethod
    async def complete(self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]) -> T:
        ...

    async def complete_with_usage(
        self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]
    ) -> tuple[T, Optional[dict[str, Any]]]:
        """Variante rapportant l'`usage` du fournisseur (T8.5) : (sortie, usage ou None).
        Par défaut : `complete()` sans usage rapporté."""
        return await self.complete(role, prompt, input_data, response_model), None

    def estimate_input_tokens(self, prompt: str, input_data: dict[str, Any]) -> int:
        """Estimation conservative des tokens d'entrée (~4 caractères par token)."""
        return max(1, (len(prompt) + len(json.dumps(input_data, ensure_ascii=False, default=str))) // 4)

    def estimate_cost_cents(self, input_tokens: int, max_output_tokens: Optional[int]) -> Optional[int]:
        """Borne de coût de l'appel avant envoi (T8.4) ; None = non bornable (refusé)."""
        return self.cost_per_call_cents

    def actual_cost_cents(self, usage: Optional[dict[str, Any]]) -> Optional[int]:
        """Coût constaté à partir de l'usage réel (T8.5) ; None = inconnu (à réconcilier)."""
        return self.cost_per_call_cents if self.paid else None

    async def ping(self) -> dict:
        """Test de connexion explicite (D2 §4.2). Par défaut : adaptateur sans point de contrôle
        réseau (simulé). Aucun appel facturable n'est lancé par un ping (B6)."""
        return {"ok": True, "provider": self.provider, "model": self.model, "paid": self.paid, "models": [self.model]}
