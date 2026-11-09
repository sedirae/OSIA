from __future__ import annotations

import asyncio
from dataclasses import replace

from .ai import AIBroker, ChatCompletionsAdapter, build_ai_adapters
from .ai.connections import AIConnections, CONFIG_SETTING, ConnectionsState
from .backup import BackupService
from .config import ConfigError, Settings
from .connectors import ConnectorHealthChecker, ConnectorRegistry, SimulatedConnector
from .connectors.real import build_real_connectors
from .events import EventBus
from .exchange import ExchangeService
from .netguard import NetworkGuard, NetworkPolicy
from .nethttp import close_default_session_pool
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
from .techlog import TechLog


class Engine:
    """Façade du moteur (monolithe modulaire, T3.2) : assemble les modules du socle."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = None
        # EXEC-06 : dernière version connue (renseignée par le check de démarrage,
        # exposé via GET /api/v1/system/version) — None = non vérifié / indisponible.
        self.latest_version: str | None = None
        self.repo: Repo
        self.bus: EventBus
        self.budgets: BudgetManager
        self.policy: PolicyEngine
        self.registry: ConnectorRegistry
        self.broker: AIBroker
        self.ai_connections: AIConnections
        self.filestore: FileStore
        self.graph: GraphService
        self.report: ReportService
        self.exchange: ExchangeService
        self.backup: BackupService
        self.orchestrator: Orchestrator
        self.scheduler: Scheduler
        self.audit: SecurityAudit
        self.techlog: TechLog
        self.sessions: SessionManager
        self.netguard: NetworkGuard
        self.secrets: SecretStore
        self.health: ConnectorHealthChecker
        self.external_semaphore: asyncio.Semaphore
        self._runner: asyncio.Task | None = None
        # EXEC-06 : tâche de fond du check de version au démarrage (await dans stop()).
        self._version_check_task: asyncio.Task | None = None

    async def setup(self) -> None:
        self.settings.paths.ensure()
        self.pool = await create_pool(self.settings.db_dsn)
        try:
            await self._setup_components()
        except BaseException:
            await self.pool.close()
            raise

    async def _setup_components(self) -> None:
        await migrate(self.pool)
        self.repo = Repo(self.pool)
        await self.repo.set_setting("paid_calls_enabled", await self.repo.get_setting("paid_calls_enabled", False))
        await self.repo.set_setting(
            "global_monthly_cap_cents", await self.repo.get_setting("global_monthly_cap_cents", self.settings.global_monthly_cap_cents)
        )
        await self.repo.set_setting("timezone", await self.repo.get_setting("timezone", self.settings.timezone))
        # CON-13 / V1.4 : TTL du cache technique des requêtes source (24 h par défaut)
        await self.repo.set_setting("source_cache_ttl_hours", await self.repo.get_setting("source_cache_ttl_hours", 24))
        # CON-18 / T3.13 : rétention du journal technique (distincte de l'audit de sécurité)
        await self.repo.set_setting(
            "tech_log_retention_days",
            await self.repo.get_setting("tech_log_retention_days", self.settings.tech_log_retention_days),
        )
        # CON-13 / D7 §9.1 : les paramètres administrables sont seedés pour exposer leur valeur
        # effective (GET /api/v1/settings) dès le premier démarrage
        await self.repo.set_setting("audit_retention_days", await self.repo.get_setting("audit_retention_days", self.settings.audit_retention_days))
        await self.repo.set_setting("session_ttl_hours", await self.repo.get_setting("session_ttl_hours", self.settings.session_ttl_hours))
        self.bus = EventBus(self.repo)
        self.budgets = BudgetManager(self.pool)
        self.registry = ConnectorRegistry()
        self.policy = PolicyEngine(self.pool, self.budgets)
        self.filestore = FileStore(self.pool, self.settings.paths)
        self.external_semaphore = asyncio.Semaphore(2)
        self.audit = SecurityAudit(
            self.settings.paths.log_dir,
            retention_days=await self.repo.get_setting("audit_retention_days", self.settings.audit_retention_days),
        )
        self.techlog = TechLog(
            self.settings.paths.log_dir,
            retention_days=await self.repo.get_setting("tech_log_retention_days", self.settings.tech_log_retention_days),
        )
        self.sessions = SessionManager(
            self.pool, ttl_hours=await self.repo.get_setting("session_ttl_hours", self.settings.session_ttl_hours),
        )
        self.secrets = SecretStore(self.settings.paths.config_dir, persist=self.settings.secrets_persist)
        connector = SimulatedConnector()
        self.registry.register(connector)
        self.policy.allow_target(connector.manifest.id)
        # CON-11 (V1.3) : adaptateurs IA réels selon la configuration ; CON-07/CON-08 : connecteurs
        # réels V1.2. Leurs domaines alimentent l'allowlist du NetworkGuard AVANT sa création.
        ai_state = ConnectionsState.model_validate(await self.repo.get_setting(CONFIG_SETTING, {}))
        ai_settings = replace(self.settings, ai_provider_explicit=False) if ai_state.selected is not None else self.settings
        ai_adapters, role_models, ai_domains = build_ai_adapters(ai_settings, self.secrets)
        real_connectors = build_real_connectors()
        allowed_domains = set(self.settings.net_allow_domains)
        for entry in self.registry.list():
            allowed_domains.update(entry.get("domains", []))
        for c in real_connectors:
            allowed_domains.update(c.manifest.domains)
        allowed_domains.update(ai_domains)
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
        for entry in self.registry.list():
            enabled = await self.repo.get_setting(f"connector_enabled:{entry['id']}", entry["enabled"])
            self.registry.set_enabled(entry["id"], enabled is True)
        for ad in ai_adapters.values():
            if isinstance(ad, ChatCompletionsAdapter) and not getattr(ad, "is_local", False):
                ad.netguard = self.netguard  # host externe (ex. api.mistral.ai) : guard T5.4
            self.policy.allow_target(f"{ad.provider}:{ad.model}")
        self.broker = AIBroker(
            self.policy,
            self.bus,
            ai_adapters,
            role_models=role_models,
            semaphore=self.external_semaphore,
            techlog=self.techlog,
        )
        self.ai_connections = AIConnections(self.settings, self.repo, self.broker, self.netguard)
        await self.ai_connections.restore(ai_state)
        self.health = ConnectorHealthChecker(self.registry)
        self.graph = GraphService(self.pool, self.repo, self.bus, registry=self.registry)
        self.report = ReportService(self.pool, self.repo, graph=self.graph)
        self.exchange = ExchangeService(self.pool, self.repo, self.bus, self.filestore, self.settings.paths, report=self.report)
        self.backup = BackupService(self.pool, self.repo, self.bus, self.settings.paths, self.settings)
        self.orchestrator = Orchestrator(self.pool, self.repo, self.bus, budgets=self.budgets)
        self.scheduler = Scheduler(self.pool, self.repo, self.bus, DEFAULT_HANDLERS, self)
        self.techlog.log("engine", "engine.setup", detail={"mode": self.settings.mode})

    async def start(self) -> dict:
        # Un deuxième serveur/CLI ne doit jamais récupérer les tâches du moteur vivant.
        if self._runner is not None and not self._runner.done():
            raise ConfigError("Un moteur OSIA est déjà actif sur cette base.")
        connection = await self.pool.acquire()
        locked = False
        try:
            locked = await connection.fetchval("SELECT pg_try_advisory_lock(hashtext('osia:scheduler'))")
            if not locked:
                raise ConfigError("Un moteur OSIA est déjà actif sur cette base. Utilise le service existant.")
            recovery = await self.scheduler.recover()
        except BaseException:
            if locked:
                await connection.execute("SELECT pg_advisory_unlock(hashtext('osia:scheduler'))")
            await self.pool.release(connection)
            raise

        async def run_exclusively():
            try:
                await self.scheduler.run_forever()
            finally:
                # Libéré aussi si l'ordonnanceur échoue ou est arrêté directement.
                try:
                    await connection.execute("SELECT pg_advisory_unlock(hashtext('osia:scheduler'))")
                finally:
                    await self.pool.release(connection)

        self.scheduler.reset_stop()
        self._runner = asyncio.create_task(run_exclusively())
        self.techlog.log("engine", "engine.start", detail={"recovered_tasks": recovery.get("recovered") if isinstance(recovery, dict) else None})
        return recovery

    async def stop(self) -> None:
        self.scheduler.stop()
        try:
            if self._runner:
                await self._runner
        finally:
            if self._version_check_task:
                self._version_check_task.cancel()
                await asyncio.gather(self._version_check_task, return_exceptions=True)
            if self.pool:
                await self.pool.close()
            await close_default_session_pool()
            self.techlog.log("engine", "engine.stop")
