from __future__ import annotations

import json

import asyncio
from typing import Any, Optional

from .models import Event
from .store.repo import Repo


class SubscriberQueue(asyncio.Queue):
    """File d'abonné SSE (audit F15) : compte les événements PERDUS par saturation
    (maxsize atteint) — jamais de perte silencieuse, le consommateur se resynchronise."""

    def __init__(self, maxsize: int = 1000):
        super().__init__(maxsize=maxsize)
        self.dropped = 0


class EventBus:
    """Journal persistant (table events) + diffusion in-process pour SSE (T3.13/T4.9, EXEC-04)."""

    def __init__(self, repo: Repo):
        self.repo = repo
        self._subscribers: set[asyncio.Queue] = set()

    async def emit(
        self,
        *,
        type: str,
        investigation_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        row = await self.repo.append_event(
            type=type, investigation_id=investigation_id, branch_id=branch_id, payload=payload
        )
        event = Event(
            id=row["id"],
            investigation_id=row["investigation_id"],
            branch_id=row["branch_id"],
            type=row["type"],
            payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
            created_at=row["created_at"],
        )
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # F15 : saturation -> on compte la perte (jamais silencieuse) ; le consommateur
                # SSE détecte `dropped` et se resynchronise depuis la base.
                if isinstance(queue, SubscriberQueue):
                    queue.dropped += 1
        return event

    def subscribe(self, investigation_id: str) -> SubscriberQueue:
        queue = SubscriberQueue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
