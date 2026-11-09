from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..config import Settings, is_local_host
from ..models import ApiError
from ..netguard import NetworkGuard
from ..store.repo import Repo
from .broker import AIBroker
from .real import DEFAULT_LOCAL_BASE_URL, DEFAULT_MISTRAL_API_BASE, MODEL_PATTERN, ChatCompletionsAdapter


ProviderKey = Literal["mistral", "local", "compatible"]
PROVIDER_KEYS = ("mistral", "local", "compatible")
CONFIG_SETTING = "ai_connections"


class ConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(pattern=MODEL_PATTERN)
    base_url: str | None = Field(default=None, max_length=512)
    input_cents_per_mtok: int | None = Field(default=None, strict=True, ge=0, le=100_000_000)
    output_cents_per_mtok: int | None = Field(default=None, strict=True, ge=0, le=100_000_000)


class ConnectionCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, max_length=512)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)

    def key_value(self) -> str | None:
        value = self.api_key.get_secret_value() if self.api_key is not None else None
        if value is not None and not re.fullmatch(r"[!-~]+", value):
            raise ApiError("invalid_key", "La clé API contient des caractères non autorisés.", 422)
        return value


class ConnectionUpdate(ConnectionConfig, ConnectionCredentials):
    pass


class ConnectionsState(BaseModel):
    selected: Literal["simulated", "mistral", "local", "compatible"] | None = None
    providers: dict[ProviderKey, ConnectionConfig] = Field(default_factory=dict)


def _api_base(key: ProviderKey, value: str | None) -> str:
    if key == "mistral":
        if value not in (None, DEFAULT_MISTRAL_API_BASE):
            raise ApiError("invalid_endpoint", "Utilise l’adresse officielle de Mistral.", 422)
        return DEFAULT_MISTRAL_API_BASE

    value = value or ""
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        raise ApiError("invalid_endpoint", "L’adresse de l’API est invalide.", 422) from None
    if (
        not host or not re.fullmatch(r"[A-Za-z0-9:/.[\]_~-]+", value)
        or (port is not None and port == 0)
        or parsed.path.rstrip("/").endswith(("/chat/completions", "/models"))
        or any(segment in (".", "..") for segment in parsed.path.split("/"))
    ):
        raise ApiError("invalid_endpoint", "Indique l’adresse de base de l’API, par exemple https://api.openai.com/v1.", 422)
    if key == "local":
        if parsed.scheme not in ("http", "https") or not is_local_host(host):
            raise ApiError("invalid_endpoint", "Un fournisseur local doit écouter sur la boucle locale du serveur OSIA.", 422)
        # Une adresse littérale évite une résolution DNS hors du garde réseau.
        if host == "localhost":
            host = "127.0.0.1"
    elif parsed.scheme != "https" or not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z][a-z0-9-]*", host):
        raise ApiError("invalid_endpoint", "Utilise une adresse HTTPS avec un nom de domaine public.", 422)
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


class AIConnections:
    """Configuration web CON-11. Les métadonnées survivent au redémarrage, les clés saisies restent en mémoire."""

    def __init__(self, settings: Settings, repo: Repo, broker: AIBroker, netguard: NetworkGuard):
        self.settings = settings
        self.repo = repo
        self.broker = broker
        self.netguard = netguard
        self.state = ConnectionsState()
        self.lock = asyncio.Lock()

    async def restore(self, state: ConnectionsState) -> None:
        self.state = state
        for key, config in state.providers.items():
            self._install(key, self._adapter(key, config))
        if state.selected is not None:
            self._route(state.selected)
        self.refresh_fallback(await self.repo.get_setting("allow_ai_fallback_local_to_cloud", False))

    def view(self) -> dict:
        configurations = {}
        defaults = {
            "mistral": {
                "model": self.settings.mistral_model, "base_url": DEFAULT_MISTRAL_API_BASE,
                "input_cents_per_mtok": self.settings.mistral_input_cents_per_mtok,
                "output_cents_per_mtok": self.settings.mistral_output_cents_per_mtok,
            },
            "local": {"model": self.settings.ai_local_model, "base_url": DEFAULT_LOCAL_BASE_URL},
            "compatible": {"base_url": "https://api.openai.com/v1", "model": ""},
        }
        for key, default in defaults.items():
            adapter = self.broker.adapters.get(key)
            config = self.state.providers.get(key, default)
            data = config.model_dump() if isinstance(config, ConnectionConfig) else config
            server_endpoint = False
            if isinstance(adapter, ChatCompletionsAdapter) and key not in self.state.providers:
                try:
                    base = _api_base(key, adapter.base_url)
                except ApiError:
                    # Un endpoint historique peut contenir des identifiants ou des paramètres.
                    server_endpoint = True
                else:
                    data = {**data, "base_url": base, "model": adapter.model}
            configurations[key] = {
                **data,
                "ready": adapter is not None,
                "server_endpoint": server_endpoint,
                "has_key": (isinstance(adapter, ChatCompletionsAdapter) and adapter.base_url == data["base_url"]
                            and bool(adapter.api_key)),
            }
        selected = self.broker.role_models.get("planning", "simulated")
        active = self.broker.adapters.get(selected)
        return {
            "configurations": configurations,
            "selected": selected,
            "active_model": active.model if active else None,
        }

    def _adapter(self, key: ProviderKey, config: ConnectionConfig, api_key: str | None = None) -> ChatCompletionsAdapter | None:
        base = _api_base(key, config.base_url)
        previous = self.broker.adapters.get(key)
        if api_key is None and isinstance(previous, ChatCompletionsAdapter) and previous.base_url == base:
            api_key = previous.api_key
        paid = key != "local"
        if paid and not api_key:
            return None
        guard = None
        if paid:
            host = urlsplit(base).hostname
            try:
                policy = replace(
                    self.netguard.policy, allowed_domains={host}, max_redirects=0, public_only=True,
                    timeout_seconds=self.settings.ai_timeout_seconds,
                )
                guard = NetworkGuard(policy, audit=self.netguard.audit)
            except ValueError:
                raise ApiError("invalid_endpoint", "Le domaine de l’API est invalide.", 422) from None
        return ChatCompletionsAdapter(
            provider=key, model=config.model, base_url=base, api_key=api_key, paid=paid, netguard=guard,
            timeout_seconds=self.settings.ai_timeout_seconds, max_output_tokens=self.settings.ai_max_output_tokens,
            input_cents_per_mtok=config.input_cents_per_mtok, output_cents_per_mtok=config.output_cents_per_mtok,
        )

    def _install(self, key: str, adapter: ChatCompletionsAdapter | None) -> None:
        if adapter is None:
            self.broker.adapters.pop(key, None)
        else:
            self.broker.adapters[key] = adapter

    def _route(self, key: str) -> None:
        self.broker.role_models = {role: key for role in self.broker.role_models}

    def refresh_fallback(self, allowed: bool) -> None:
        adapters = self.broker.adapters
        self.broker.allowed_fallbacks = {"local": "mistral"} if allowed and {"local", "mistral"} <= adapters.keys() else {}

    async def _ensure_idle(self) -> None:
        if await self.repo.pool.fetchval("SELECT EXISTS (SELECT 1 FROM investigations WHERE state = 'running')"):
            raise ApiError("investigation_running", "Termine ou suspends les investigations en cours avant de modifier le fournisseur ou le modèle.", 409)

    async def _save(self, state: ConnectionsState) -> None:
        await self.repo.set_setting(CONFIG_SETTING, state.model_dump())
        self.state = state

    async def configure(self, key: ProviderKey, body: ConnectionUpdate) -> None:
        async with self.lock:
            base = _api_base(key, body.base_url)
            config = ConnectionConfig.model_validate({**body.model_dump(exclude={"api_key"}), "base_url": base})
            adapter = self._adapter(key, config, body.key_value())
            if adapter is None:
                raise ApiError("missing_api_key", "Renseigne une clé API pour cette adresse.", 422)
            if key in self.broker.role_models.values() or key in self.broker.allowed_fallbacks.values():
                previous = self.broker.adapters.get(key)
                saved = self.state.providers.get(key)
                previous_base = previous.base_url if isinstance(previous, ChatCompletionsAdapter) else (saved.base_url if saved else None)
                if previous_base is not None and previous_base != base:
                    raise ApiError("provider_in_use", "Sélectionne un autre fournisseur et désactive le repli éventuel avant de changer cette adresse.", 409)
                if saved != config:
                    await self._ensure_idle()
                self._ensure_pricing(adapter)
            fallback_allowed = await self.repo.get_setting("allow_ai_fallback_local_to_cloud", False)
            await self._save(self.state.model_copy(update={"providers": {**self.state.providers, key: config}}))
            self._install(key, adapter)
            self.refresh_fallback(fallback_allowed)

    def test_adapter(self, key: ProviderKey, body: ConnectionCredentials) -> ChatCompletionsAdapter:
        adapter = self._adapter(key, ConnectionConfig(model="connection-test", base_url=body.base_url), body.key_value())
        if adapter is None:
            raise ApiError("missing_api_key", "Renseigne une clé API pour cette adresse.", 422)
        return adapter

    @staticmethod
    def _ensure_pricing(adapter: ChatCompletionsAdapter) -> None:
        if adapter.paid and (adapter.input_cents_per_mtok is None or adapter.output_cents_per_mtok is None
                             or not (adapter.input_cents_per_mtok or adapter.output_cents_per_mtok)):
            raise ApiError("missing_pricing", "Renseigne les tarifs d’entrée et de sortie avant d’utiliser ce fournisseur cloud.", 422)

    async def select(self, key: str) -> None:
        async with self.lock:
            adapter = self.broker.adapters.get(key)
            if adapter is None:
                raise ApiError("provider_unavailable", "Configure le fournisseur et sa clé API avant de le sélectionner.", 409)
            if isinstance(adapter, ChatCompletionsAdapter) and key in self.state.providers:
                self._ensure_pricing(adapter)
            if key != self.broker.role_models.get("planning"):
                await self._ensure_idle()
            await self._save(self.state.model_copy(update={"selected": key}))
            self._route(key)

    def ensure_ready(self) -> None:
        if any(key not in self.broker.adapters for key in self.broker.role_models.values()):
            raise ApiError("provider_unavailable", "Le fournisseur actif attend sa clé API. Ouvre Paramètres → Fournisseurs IA.", 409)
