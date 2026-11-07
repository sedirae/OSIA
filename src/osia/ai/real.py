from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel

from ..config import Settings, is_local_host
from ..netguard import NetworkGuard
from ..security import SecretStore
from .base import AIAdapter
from .simulated import SimulatedAIAdapter

T = TypeVar("T", bound=BaseModel)

DEFAULT_MISTRAL_MODEL = "mistral-small-2603"  # V1.3 : Mistral Small 4
DEFAULT_LOCAL_MODEL = "ministral-3-8b"  # V1.3 : premier candidat local à qualifier
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"  # endpoint OpenAI-compatible local (Ollama…)
DEFAULT_MISTRAL_API_BASE = "https://api.mistral.ai/v1"

# Contrat d'un fetch POST injecté (tests hors ligne) : (url, payload, headers) -> (status, headers, body).
PostFetchFn = Callable[[str, Optional[dict], dict], Awaitable[tuple[int, dict, bytes]]]


class AIAdapterError(Exception):
    """Échec d'appel fournisseur. Le message ne contient JAMAIS la clé API ni les headers (T8.8)."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _aiohttp_post(payload: dict, headers: dict, timeout: int) -> Callable[[str], Awaitable[tuple[int, dict, bytes]]]:
    """Fetch POST réel (aiohttp), sans suivre les redirections (gérées par le guard)."""

    async def fetch(url: str) -> tuple[int, dict, bytes]:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, json=payload, headers=headers, allow_redirects=False) as resp:
                body = await resp.read()
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body

    return fetch


def _aiohttp_get(headers: dict, timeout: int) -> Callable[[str], Awaitable[tuple[int, dict, bytes]]]:
    async def fetch(url: str) -> tuple[int, dict, bytes]:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url, headers=headers, allow_redirects=False) as resp:
                body = await resp.read()
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body

    return fetch


class ChatCompletionsAdapter(AIAdapter):
    """Adaptateur fournisseur compatible chat completions (Mistral cloud, LLM local OpenAI-compatible).

    - Toute requête sortante vers un host EXTERNE passe par le NetworkGuard (T5.4) ; un endpoint
      local explicite (127.0.0.1/localhost/::1) reste hors guard (liaison locale, T1).
    - `fetch_fn` injectable pour les tests hors ligne (aucun appel réel, AGENTS.md).
    - La clé API n'est jamais journalisée, ni dans les prompts, ni dans les exceptions (T8.8, D2 §4.3).
    - Sortie structurée : `response_format json_object` + validation pydantic (T8.6) ; une sortie
      invalide lève ValidationError, rejetée par le courtier (sortie_ia_invalide).
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
        paid: bool = False,
        cost_per_call_cents: Optional[int] = None,
        netguard: Optional[NetworkGuard] = None,
        fetch_fn: Optional[PostFetchFn] = None,
        timeout_seconds: int = 60,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.paid = paid
        self.cost_per_call_cents = cost_per_call_cents
        self.netguard = netguard
        self.fetch_fn = fetch_fn
        self.timeout_seconds = timeout_seconds
        self.host = urlparse(self.base_url).hostname or ""

    @property
    def completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": "osia/0.1 (+investigation-osint)"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post(self, url: str, payload: dict) -> tuple[int, dict, bytes]:
        if self.fetch_fn is not None:
            return await self.fetch_fn(url, payload, self._headers())
        fetch = _aiohttp_post(payload, self._headers(), self.timeout_seconds)
        if self.netguard is not None:
            return await self.netguard.guarded_request(fetch, url)
        return await fetch(url)

    async def _get(self, url: str) -> tuple[int, dict, bytes]:
        if self.fetch_fn is not None:
            return await self.fetch_fn(url, None, self._headers())
        fetch = _aiohttp_get(self._headers(), self.timeout_seconds)
        if self.netguard is not None:
            return await self.netguard.guarded_request(fetch, url)
        return await fetch(url)

    async def complete(self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]) -> T:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(input_data, ensure_ascii=False, default=str)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        status, _, body = await self._post(self.completions_url, payload)
        if status != 200:
            raise AIAdapterError(f"fournisseur {self.provider} : HTTP {status}", status=status)
        try:
            data = json.loads(body.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, UnicodeDecodeError) as exc:
            raise AIAdapterError(f"fournisseur {self.provider} : réponse illisible (pas de choices[0].message.content)", status=status) from exc
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:  # TypeError : content null ou non str
            raise AIAdapterError(f"fournisseur {self.provider} : sortie non JSON (T8.6)", status=status) from exc
        # ValidationError propagée : le courtier rejette la sortie (T8.6, sortie_ia_invalide)
        return response_model.model_validate(parsed)

    async def ping(self) -> dict:
        """Test de connexion explicite (D2 §4.2) : GET /models — listing non facturé, aucun prompt
        métier transmis. Aucun appel facturable n'est lancé ici (B6 : pas d'appel payant hors
        enveloppe autorisée)."""
        status, _, body = await self._get(self.models_url)
        if status != 200:
            raise AIAdapterError(f"fournisseur {self.provider} : test de connexion HTTP {status}", status=status)
        try:
            data = json.loads(body.decode("utf-8"))
            raw = data.get("data", data.get("models", []))
            models = [m.get("id") for m in raw if isinstance(m, dict) and m.get("id")]
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError) as exc:
            raise AIAdapterError(f"fournisseur {self.provider} : liste des modèles illisible", status=status) from exc
        return {"ok": True, "provider": self.provider, "model": self.model, "paid": self.paid, "models": models}


class MistralCloudAdapter(ChatCompletionsAdapter):
    """Mistral API cloud (V1.3) : modèle Small 4 `mistral-small-2603` par défaut, payant.

    La clé API provient de `OSIA_MISTRAL_API_KEY` ou du coffre de secrets (`MISTRAL_API_KEY`) —
    jamais persistée en clair hors coffre chiffré, jamais dans les logs/exports/prompts (D2 §4.3).
    Le coût par appel est une BORNE estimée (T8.4 : réservation avant l'appel) ; configurable."""

    def __init__(self, *, api_key: str, model: str = DEFAULT_MISTRAL_MODEL, base_url: str = DEFAULT_MISTRAL_API_BASE,
                 cost_per_call_cents: int = 5, **kw):
        super().__init__(
            provider="mistral",
            model=model,
            base_url=base_url,
            api_key=api_key,
            paid=True,
            cost_per_call_cents=cost_per_call_cents,
            **kw,
        )


class LocalOpenAIAdapter(ChatCompletionsAdapter):
    """LLM local compatible OpenAI (V1.3) : endpoint configurable (Ollama…), non payant.

    Préférence T8.8 : les données restent locales par défaut. Un host local explicite
    (127.0.0.1/localhost/::1) reste hors NetworkGuard (liaison locale T1) ; tout autre host
    passe par le guard et doit être autorisé dans l'allowlist."""

    def __init__(self, *, model: str = DEFAULT_LOCAL_MODEL, base_url: str = DEFAULT_LOCAL_BASE_URL, **kw):
        super().__init__(provider="local", model=model, base_url=base_url, api_key=None, paid=False, **kw)
        self.is_local = is_local_host(self.host)
        if self.is_local:
            self.netguard = None  # endpoint local explicite : pas de guard externe (T1)


def build_ai_adapters(settings: Settings, secrets: Optional[SecretStore]) -> tuple[dict[str, AIAdapter], dict[str, str], set[str]]:
    """Construit les adaptateurs IA disponibles (D2 §4.2, V1.3) selon la configuration.

    Retourne (adaptateurs par clé, modèles par rôle, domaines externes à autoriser).
    - `simulated` toujours présent (développement/tests, T3.14) ;
    - `local` si `OSIA_AI_LOCAL_BASE_URL` est défini ;
    - `mistral` si une clé est disponible (env `OSIA_MISTRAL_API_KEY` ou coffre `MISTRAL_API_KEY`) ;
    - rôle par défaut : `OSIA_AI_PROVIDER` (simulé par défaut — aucun appel payant sans
      configuration explicite, B6/V1.4 : budget 0 € au premier démarrage)."""
    adapters: dict[str, AIAdapter] = {"simulated": SimulatedAIAdapter()}
    domains: set[str] = set()
    if settings.ai_local_base_url:
        local = LocalOpenAIAdapter(model=settings.ai_local_model, base_url=settings.ai_local_base_url, timeout_seconds=settings.ai_timeout_seconds)
        adapters["local"] = local
        if not local.is_local and local.host:
            domains.add(local.host)
    api_key = os.environ.get("OSIA_MISTRAL_API_KEY") or (secrets.get("MISTRAL_API_KEY") if secrets is not None else None)
    if api_key:
        adapters["mistral"] = MistralCloudAdapter(
            api_key=api_key,
            model=settings.mistral_model,
            base_url=settings.mistral_api_base,
            cost_per_call_cents=settings.mistral_cost_cents,
            timeout_seconds=settings.ai_timeout_seconds,
        )
        host = urlparse(settings.mistral_api_base).hostname
        if host:
            domains.add(host)
    provider = settings.ai_provider if settings.ai_provider in adapters else "simulated"
    role_models = {role: provider for role in ("planning", "extraction", "synthesis")}
    return adapters, role_models, domains
