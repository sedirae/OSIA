from __future__ import annotations

import asyncio
import time
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
        techlog: Optional[Any] = None,
    ):
        self.engine = engine
        self.bus = bus
        self.adapters = adapters
        self.role_models = role_models
        self.allowed_fallbacks = allowed_fallbacks or {}
        self.semaphore = semaphore
        self.techlog = techlog  # CON-18 / T3.13 : journal technique structuré (durées, consommations)
        # Un verrou par cible d'adaptateur : l'état partagé de l'adaptateur (ex. last_usage)
        # n'est jamais écrasé par deux appels concurrents sur le même fournisseur (P3-1).
        self._locks: dict[str, asyncio.Lock] = {}

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
        # F03 / T8.4 : borne calculée depuis les tarifs token (entrée estimée + plafond de sortie),
        # jamais un forfait presented comme réel ; None = non bornable -> refusé par le moteur.
        estimate = (
            adapter.estimate_cost_cents(adapter.estimate_input_tokens(prompt, input_data), adapter.max_output_tokens)
            if adapter.paid
            else None
        )
        decision = await self.engine.authorize(
            investigation_id=investigation_id,
            kind=OpKind.AI_CALL,
            target=target,
            is_paid=adapter.paid,
            cost_estimated_cents=estimate,
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
            payload={"op_id": op_id, "kind": "ai_call", "target": target, "reservation_id": decision.reservation_id, "estimated_cents": estimate},
        )
        started = time.monotonic()
        usage: Optional[dict[str, Any]] = None
        # Un verrou par fournisseur : l'état partagé de l'adaptateur (ex. last_usage) n'est jamais
        # lu/écrit par deux appels concurrents sur le même adaptateur (P3-1) — les handlers
        # d'exception ci-dessous s'exécutent encore sous ce verrou.
        lock = self._locks.setdefault(target, asyncio.Lock())
        async with lock:
            try:
                if self.semaphore is not None:
                    await self.semaphore.acquire()
                try:
                    # F04 : revalidation atomique IMMÉDIATEMENT avant l'I/O (l'attente du sémaphore est
                    # incluse) — une autorisation révoquée pendant l'attente bloque l'envoi.
                    recheck = await self.engine.revalidate(op_id, investigation_id=investigation_id)
                    if not recheck.allowed:
                        await self.engine.cancel_op(op_id, reason=recheck.reason or "revalidation_refusee")
                        raise PolicyDeny(recheck.reason or "revalidation_refusee", "ai")
                    if not await self.engine.mark_in_flight(op_id):
                        # P2-1 : l'opération a été annulée entre la revalidation et l'envoi (stop) —
                        # jamais envoyée : enveloppe libérée, AUCUN appel à l'adaptateur.
                        await self.engine.cancel_op(op_id, reason="operation_annulee_avant_envoi")
                        raise PolicyDeny("operation_annulee_avant_envoi", "ai")
                    output, usage = await asyncio.wait_for(
                        adapter.complete_with_usage(role, prompt, input_data, response_model),
                        timeout=decision.timeout_seconds or 60,
                    )
                finally:
                    if self.semaphore is not None:
                        self.semaphore.release()
            except ValidationError as exc:
                # F03 : la sortie métier est rejetée MAIS l'appel a été envoyé et peut être facturé —
                # réconciliation avec le coût réel si l'usage est connu, sinon op 'uncertain'.
                actual = adapter.actual_cost_cents(getattr(adapter, "last_usage", usage)) if adapter.paid else None
                if decision.reservation_id and actual is not None:
                    await self.engine.fail_op_billed(op_id, f"sortie_invalide:{exc.error_count()}", actual_cents=actual)
                elif decision.reservation_id:
                    await self.engine.mark_uncertain(op_id)
                else:
                    await self.engine.fail_op(op_id, f"sortie_invalide:{exc.error_count()}")
                await self.bus.emit(
                    type="op.failed",
                    investigation_id=investigation_id,
                    branch_id=branch_id,
                    payload={"op_id": op_id, "error": "sortie IA non conforme au schéma (T8.6)"},
                )
                if self.techlog is not None:
                    self.techlog.log("ai.broker", "ai.call", level="error", investigation_id=investigation_id, branch_id=branch_id, op_id=op_id, duration_ms=int((time.monotonic() - started) * 1000), error="sortie_ia_invalide", detail={"target": target, "role": role})
                raise PolicyDeny("sortie_ia_invalide", "ai")
            except PolicyDeny:
                raise
            except Exception as exc:
                await self.engine.mark_uncertain(op_id)
                await self.bus.emit(
                    type="op.uncertain",
                    investigation_id=investigation_id,
                    branch_id=branch_id,
                    payload={"op_id": op_id, "error": str(exc)},
                )
                if self.techlog is not None:
                    self.techlog.log("ai.broker", "ai.call", level="error", investigation_id=investigation_id, branch_id=branch_id, op_id=op_id, duration_ms=int((time.monotonic() - started) * 1000), error=str(exc), detail={"target": target, "role": role})
                raise
            # F03 / T8.5 : coût CONSTATÉ depuis l'usage réel — jamais l'estimation présentée comme réel.
            actual = adapter.actual_cost_cents(usage) if adapter.paid else None
            result = {"role": role, "output": output.model_dump(mode="json")}
            if adapter.paid and actual is None:
                await self.engine.complete_op_uncertain(op_id, result)  # facturation inconnue -> réconciliation
                await self.bus.emit(
                    type="op.uncertain",
                    investigation_id=investigation_id,
                    branch_id=branch_id,
                    payload={"op_id": op_id, "error": "usage absent : facturation à réconcilier"},
                )
            else:
                await self.engine.complete_op(op_id, result, actual_cents=actual)
            if self.techlog is not None:
                self.techlog.log("ai.broker", "ai.call", investigation_id=investigation_id, branch_id=branch_id, op_id=op_id, duration_ms=int((time.monotonic() - started) * 1000), detail={"target": target, "role": role, "paid": adapter.paid, "estimated_cents": estimate, "actual_cents": actual, "usage": usage})
            await self.bus.emit(
                type="op.completed",
                investigation_id=investigation_id,
                branch_id=branch_id,
                payload={"op_id": op_id, "kind": "ai_call", "target": target, "role": role, "actual_cents": actual},
            )
            return output
