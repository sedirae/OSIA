from __future__ import annotations

import asyncio

from .ai import AIBroker, SimulatedAIAdapter
from .backup import BackupService
from .config import Settings
from .connectors import ConnectorHealthChecker, ConnectorRegistry, SimulatedConnector
from .connectors.real import build_real_connectors
from .events import EventBus
from .exchange import ExchangeService
from .netguard import NetworkGuard, NetworkPolicy
from .graph import GraphService
from .orchestrator import Orchestrator
from .policies import BudgetManager, PolicyEngine
from .report import ReportService
from .scheduler import Scheduler
from .security import SecretStore, SecurityAudit, SessionManager
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
        self.graph: GraphService
        self.report: ReportService
        self.exchange: ExchangeService
        self.backup: BackupService
        self.orchestrator: Orchestrator
        self.scheduler: Scheduler
        self.audit: SecurityAudit
        self.sessions: SessionManager
        self.netguard: NetworkGuard
        self.secrets: SecretStore
        self.health: ConnectorHealthChecker
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
        self.graph = GraphService(self.pool, self.repo, self.bus, registry=self.registry)
        self.report = ReportService(self.pool, self.repo, graph=self.graph)
        self.exchange = ExchangeService(self.pool, self.repo, self.bus, self.filestore, self.settings.paths, report=self.report)
        self.backup = BackupService(self.pool, self.repo, self.bus, self.settings.paths, self.settings)
        self.orchestrator = Orchestrator(self.pool, self.repo, self.bus)
        self.scheduler = Scheduler(self.pool, self.repo, self.bus, DEFAULT_HANDLERS, self)
        self.audit = SecurityAudit(self.settings.paths.log_dir, retention_days=self.settings.audit_retention_days)
        self.sessions = SessionManager(self.pool, ttl_hours=self.settings.session_ttl_hours)
        allowed_domains = set(self.settings.net_allow_domains)
        for entry in self.registry.list():
            allowed_domains.update(entry.get("domains", []))
        # Connecteurs réels V1.2 (CON-07/CON-08, PERIMETRE-V1 §V1.2) : leurs domaines alimentent
        # l'allowlist du NetworkGuard avant sa création, puis reçoivent le guard (T5.4).
        real_connectors = build_real_connectors()
        for c in real_connectors:
            allowed_domains.update(c.manifest.domains)
        self.netguard = NetworkGuard(
            NetworkPolicy(
                allowed_domains=allowed_domains,
                denied_domains=set(self.settings.net_deny_domains),
                max_bytes=self.settings.net_max_bytes,
            ),
            audit=self.audit,
        )
        for c in real_connectors:
            c.netguard = self.netguard
            self.registry.register(c)
            self.policy.allow_target(c.manifest.id)
        self.health = ConnectorHealthChecker(self.registry)
        self.secrets = SecretStore(self.settings.paths.config_dir, persist=self.settings.secrets_persist)

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
