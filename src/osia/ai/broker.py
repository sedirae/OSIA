from __future__ import annotations

import asyncio
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from ..events import EventBus
from ..models import OpKind, PolicyDeny
from ..policies.engine import PolicyEngine
from .base import AIAdapter

T = TypeVar("T", bound=BaseModel)


class AIBroker:
    """Courtier IA centralisé (T8.1, CON-11) : tous les appels modèles passent par ici.

    Cycle : autorisation par le PolicyEngine (transmission + budget) → réservation si payant (CON-04)
    → appel adaptateur → validation du schéma de sortie (T8.6) → persistance et événement.
    Repli uniquement vers une alternative préalablement autorisée (T8.9, V1.3).
    """

    def __init__(
        self,
        engine: PolicyEngine,
        bus: EventBus,
        adapters: dict[str, AIAdapter],
        role_models: dict[str, str],
        allowed_fallbacks: Optional[dict[str, str]] = None,
        semaphore: Optional[asyncio.Semaphore] = None,
    ):
        self.engine = engine
        self.bus = bus
        self.adapters = adapters
        self.role_models = role_models
        self.allowed_fallbacks = allowed_fallbacks or {}
        self.semaphore = semaphore

    def _target(self, adapter: AIAdapter) -> str:
        return f"{adapter.provider}:{adapter.model}"

    async def call(
        self,
        role: str,
        prompt: str,
        input_data: dict[str, Any],
        response_model: Type[T],
        *,
        investigation_id: str,
        branch_id: Optional[str] = None,
        task_id: Optional[str] = None,
        depth: int = 0,
    ) -> T:
        adapter_key = self.role_models.get(role, next(iter(self.adapters)))
        adapter = self.adapters[adapter_key]
        try:
            return await self._call_adapter(adapter, role, prompt, input_data, response_model, investigation_id, branch_id, task_id, depth)
        except Exception as exc:
            fallback_key = self.allowed_fallbacks.get(adapter_key)
            if fallback_key is None or fallback_key == adapter_key:
                raise
            fallback = self.adapters[fallback_key]
            await self.bus.emit(
                type="ai.fallback",
                investigation_id=investigation_id,
                branch_id=branch_id,
                payload={"from": self._target(adapter), "to": self._target(fallback), "reason": str(exc)},
            )
            return await self._call_adapter(fallback, role, prompt, input_data, response_model, investigation_id, branch_id, task_id, depth)

    async def _call_adapter(
        self,
        adapter: AIAdapter,
        role: str,
        prompt: str,
        input_data: dict[str, Any],
        response_model: Type[T],
        investigation_id: str,
        branch_id: Optional[str],
        task_id: Optional[str],
        depth: int,
    ) -> T:
        target = self._target(adapter)
        self.engine.allow_target(target)
        decision = await self.engine.authorize(
            investigation_id=investigation_id,
            kind=OpKind.AI_CALL,
            target=target,
            is_paid=adapter.paid,
            cost_estimated_cents=adapter.cost_per_call_cents,
            branch_id=branch_id,
            task_id=task_id,
            depth=depth,
        )
        if not decision.allowed:
            raise PolicyDeny(decision.reason or "refus_politique", "ai")
        op_id = decision.op_id
        await self.bus.emit(
            type="op.authorized" if not decision.reservation_id else "op.reserved",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"op_id": op_id, "kind": "ai_call", "target": target, "reservation_id": decision.reservation_id},
        )
        await self.engine.mark_in_flight(op_id)
        try:
            if self.semaphore is not None:
                async with self.semaphore:
                    output = await adapter.complete(role, prompt, input_data, response_model)
            else:
                output = await adapter.complete(role, prompt, input_data, response_model)
        except ValidationError as exc:
            await self.engine.fail_op(op_id, f"sortie_invalide:{exc.error_count()}")
            await self.bus.emit(
                type="op.failed",
                investigation_id=investigation_id,
                branch_id=branch_id,
                payload={"op_id": op_id, "error": "sortie IA non conforme au schéma (T8.6)"},
            )
            raise PolicyDeny("sortie_ia_invalide", "ai")
        except Exception as exc:
            await self.engine.mark_uncertain(op_id)
            await self.bus.emit(
                type="op.uncertain",
                investigation_id=investigation_id,
                branch_id=branch_id,
                payload={"op_id": op_id, "error": str(exc)},
            )
            raise
        actual = adapter.cost_per_call_cents if adapter.paid else None
        await self.engine.complete_op(op_id, {"role": role, "output": output.model_dump(mode="json")}, actual_cents=actual)
        await self.bus.emit(
            type="op.completed",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"op_id": op_id, "kind": "ai_call", "target": target, "role": role},
        )
        return output
