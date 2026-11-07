from __future__ import annotations

import asyncio

from .ai import AIBroker, SimulatedAIAdapter
from .config import Settings
from .connectors import ConnectorRegistry, SimulatedConnector
from .events import EventBus
from .orchestrator import Orchestrator
from .policies import BudgetManager, PolicyEngine
from .scheduler import Scheduler
from .store import create_pool, migrate
from .store.files import FileStore
from .store.repo import Repo
from .tasks import DEFAULT_HANDLERS


class Engine:
    """Façade du moteur (monolithe modulaire, T3.2) : assemble les modules du socle."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = None
        self.repo: Repo
        self.bus: EventBus
        self.budgets: BudgetManager
        self.policy: PolicyEngine
        self.registry: ConnectorRegistry
        self.broker: AIBroker
        self.filestore: FileStore
        self.orchestrator: Orchestrator
        self.scheduler: Scheduler
        self.external_semaphore: asyncio.Semaphore
        self._runner: asyncio.Task | None = None

    async def setup(self) -> None:
        self.settings.paths.ensure()
        self.pool = await create_pool(self.settings.db_dsn)
        await migrate(self.pool)
        self.repo = Repo(self.pool)
        await self.repo.set_setting("paid_calls_enabled", await self.repo.get_setting("paid_calls_enabled", False))
        await self.repo.set_setting(
            "global_monthly_cap_cents", await self.repo.get_setting("global_monthly_cap_cents", self.settings.global_monthly_cap_cents)
        )
        await self.repo.set_setting("timezone", await self.repo.get_setting("timezone", self.settings.timezone))
        self.bus = EventBus(self.repo)
        self.budgets = BudgetManager(self.pool)
        self.registry = ConnectorRegistry()
        self.policy = PolicyEngine(self.pool, self.budgets)
        self.filestore = FileStore(self.pool, self.settings.paths)
        self.external_semaphore = asyncio.Semaphore(2)
        adapter = SimulatedAIAdapter()
        self.broker = AIBroker(
            self.policy,
            self.bus,
            {"simulated": adapter},
            role_models={"planning": "simulated", "extraction": "simulated", "synthesis": "simulated"},
            allowed_fallbacks={},
            semaphore=self.external_semaphore,
        )
        for ad in self.broker.adapters.values():
            self.policy.allow_target(f"{ad.provider}:{ad.model}")
        connector = SimulatedConnector()
        self.registry.register(connector)
        self.policy.allow_target(connector.manifest.id)
        self.orchestrator = Orchestrator(self.pool, self.repo, self.bus)
        self.scheduler = Scheduler(self.pool, self.repo, self.bus, DEFAULT_HANDLERS, self)

    async def start(self) -> dict:
        recovery = await self.scheduler.recover()
        self._runner = asyncio.create_task(self.scheduler.run_forever())
        return recovery

    async def stop(self) -> None:
        self.scheduler.stop()
        if self._runner:
            await self._runner
        if self.pool:
            await self.pool.close()
