from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg

from .events import EventBus
from .models import PolicyDeny
from .store.repo import Repo
from .tasks import TaskContext, TaskHandler

if TYPE_CHECKING:
    from .engine import Engine


class Scheduler:
    """Ordonnanceur persistant PostgreSQL (T4.2, CON-03) : claim atomique SKIP LOCKED,
    reprise après incident, exécution des handlers."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        repo: Repo,
        bus: EventBus,
        handlers: dict[str, TaskHandler],
        engine: "Engine",
        poll_interval: float = 0.05,
    ):
        self.pool = pool
        self.repo = repo
        self.bus = bus
        self.handlers = handlers
        self.engine = engine
        self.poll_interval = poll_interval
        self._pending: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()

    async def recover(self) -> dict[str, int]:
        """Reprise contrôlée après incident (T3.6, T4.7, OSIA-I-09) :
        tâches interrompues remises en file, opérations externes in_flight marquées 'uncertain'
        (jamais relancées aveuglément), investigations actives suspendues."""
        async with self.pool.acquire() as conn:
            interrupted = await conn.fetch(
                "UPDATE tasks SET state = 'interrupted', updated_at = now() "
                "WHERE state IN ('claimed', 'running') RETURNING id, investigation_id"
            )
            ops = await conn.fetch(
                "UPDATE external_ops SET state = 'uncertain', updated_at = now() "
                "WHERE state IN ('reserved', 'in_flight') RETURNING id, investigation_id"
            )
            orphan_authorized = await conn.fetch(
                "UPDATE external_ops SET state = 'cancelled', updated_at = now() "
                "WHERE state = 'authorized' RETURNING id, investigation_id"
            )
            requeued = await conn.fetch(
                "UPDATE tasks SET state = 'queued', updated_at = now() WHERE state = 'interrupted' RETURNING id, investigation_id"
            )
            suspended = await conn.fetch(
                "UPDATE investigations SET state = 'suspended', stop_reason = 'crash_recovery', updated_at = now() "
                "WHERE state = 'running' RETURNING id"
            )
        for row in interrupted:
            await self.bus.emit(
                type="recovery.task_interrupted",
                investigation_id=row["investigation_id"],
                payload={"task_id": row["id"]},
            )
        for row in ops:
            await self.bus.emit(
                type="recovery.op_uncertain",
                investigation_id=row["investigation_id"],
                payload={"op_id": row["id"], "note": "jamais relancé aveuglément (OSIA-I-09)"},
            )
        for row in requeued:
            await self.bus.emit(
                type="recovery.task_requeued",
                investigation_id=row["investigation_id"],
                payload={"task_id": row["id"]},
            )
        for row in suspended:
            await self.bus.emit(
                type="recovery.investigation_suspended",
                investigation_id=row["id"],
                payload={"reason": "crash_recovery"},
            )
        return {
            "tasks_interrupted": len(interrupted),
            "ops_uncertain": len(ops),
            "ops_authorized_cancelled": len(orphan_authorized),
            "tasks_requeued": len(requeued),
            "investigations_suspended": len(suspended),
        }

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            task = await self.repo.claim_next_task()
            if task is None:
                await asyncio.sleep(self.poll_interval)
                continue
            await self.bus.emit(
                type="task.claimed",
                investigation_id=task["investigation_id"],
                branch_id=task["branch_id"],
                payload={"task_id": task["id"], "kind": task["kind"], "depth": task["depth"]},
            )
            runner = asyncio.create_task(self._execute(task))
            self._pending.add(runner)
            runner.add_done_callback(self._pending.discard)
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    def stop(self) -> None:
        self._stopping.set()

    async def _execute(self, task: asyncpg.Record) -> None:
        await self.repo.set_task_state(task["id"], "running")
        handler = self.handlers.get(task["kind"])
        if handler is None:
            await self.repo.set_task_state(task["id"], "failed", error=f"kind_inconnu:{task['kind']}", finished=True)
            return
        ctx = TaskContext(engine=self.engine)
        try:
            result = await handler(task, ctx)
        except PolicyDeny as deny:
            await self.repo.set_task_state(task["id"], "failed", error=deny.reason, finished=True)
            await self.bus.emit(
                type="task.failed",
                investigation_id=task["investigation_id"],
                branch_id=task["branch_id"],
                payload={"task_id": task["id"], "kind": task["kind"], "error": deny.reason},
            )
            await self.engine.orchestrator.on_policy_deny(task, deny)
            return
        except Exception as exc:
            await self.repo.set_task_state(task["id"], "failed", error=str(exc), finished=True)
            await self.bus.emit(
                type="task.failed",
                investigation_id=task["investigation_id"],
                branch_id=task["branch_id"],
                payload={"task_id": task["id"], "kind": task["kind"], "error": str(exc)},
            )
            return
        await self.repo.set_task_state(task["id"], "succeeded", finished=True)
        await self.bus.emit(
            type="task.succeeded",
            investigation_id=task["investigation_id"],
            branch_id=task["branch_id"],
            payload={"task_id": task["id"], "kind": task["kind"], "result": result},
        )
        await self.engine.orchestrator.on_task_succeeded(task, result)
