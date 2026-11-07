from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel

from ..config import ConfigError, Settings, is_local_host
from ..netguard import NetworkGuard, RequestContext
from ..nethttp import DEFAULT_MAX_BYTES, DEFAULT_SESSION_POOL, drop_credential_headers, read_bounded
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


def _aiohttp_post(payload: dict, headers: dict, timeout: int) -> Callable[..., Awaitable[tuple[int, dict, bytes]]]:
    """Fetch POST réel (aiohttp), sans suivre les redirections (gérées par le guard).

    Le fetch accepte un `ctx` (accepts_ctx, F02) : IPs validées épinglées au transport, lecture
    bornée, et suppression des credentials (Authorization…) sur redirection inter-origines —
    la clé API ne quitte jamais l'origine du fournisseur (T8.8)."""

    async def fetch(url: str, ctx: Optional[RequestContext] = None) -> tuple[int, dict, bytes]:
        hdrs = drop_credential_headers(headers, ctx)
        max_bytes = ctx.max_bytes if ctx is not None else DEFAULT_MAX_BYTES
        pinned = ctx.pinned if ctx is not None else None
        # Réserve audit PR#18 : session poolée (clé = host épinglé) au lieu d'une par appel.
        key = pinned.host if pinned is not None else urlparse(url).hostname or "default"
        session = await DEFAULT_SESSION_POOL.session(key, pinned=pinned, timeout=aiohttp.ClientTimeout(total=timeout))
        async with session.post(url, json=payload, headers=hdrs, allow_redirects=False) as resp:
            body = await read_bounded(resp, max_bytes, urlparse(url).hostname or "")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body

    fetch.accepts_ctx = True
    return fetch


def _aiohttp_get(headers: dict, timeout: int) -> Callable[..., Awaitable[tuple[int, dict, bytes]]]:
    """Fetch GET réel (aiohttp) ; mêmes garanties que `_aiohttp_post` (F02, T8.8)."""

    async def fetch(url: str, ctx: Optional[RequestContext] = None) -> tuple[int, dict, bytes]:
        hdrs = drop_credential_headers(headers, ctx)
        max_bytes = ctx.max_bytes if ctx is not None else DEFAULT_MAX_BYTES
        pinned = ctx.pinned if ctx is not None else None
        # Réserve audit PR#18 : session poolée (clé = host épinglé) au lieu d'une par appel.
        key = pinned.host if pinned is not None else urlparse(url).hostname or "default"
        session = await DEFAULT_SESSION_POOL.session(key, pinned=pinned, timeout=aiohttp.ClientTimeout(total=timeout))
        async with session.get(url, headers=hdrs, allow_redirects=False) as resp:
            body = await read_bounded(resp, max_bytes, urlparse(url).hostname or "")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body

    fetch.accepts_ctx = True
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
        input_cents_per_mtok: Optional[int] = None,
        output_cents_per_mtok: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.input_cents_per_mtok = input_cents_per_mtok
        self.output_cents_per_mtok = output_cents_per_mtok
        self.max_output_tokens = max_output_tokens
        self.last_usage: Optional[dict[str, Any]] = None  # usage du dernier appel (T8.5, F03)
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

    def _payload(self, prompt: str, input_data: dict[str, Any]) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(input_data, ensure_ascii=False, default=str)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        # F03 / T8.4 : plafond de tokens de sortie envoyé au fournisseur (borne garantie côté API)
        if self.max_output_tokens:
            payload["max_tokens"] = self.max_output_tokens
        return payload

    def estimate_cost_cents(self, input_tokens: int, max_output_tokens: Optional[int]) -> Optional[int]:
        """Borne de coût calculée depuis les tarifs token (T8.4, F03) : entrée estimée + plafond
        de sortie. Repli sur le forfait `cost_per_call_cents` si les tarifs sont inconnus ;
        None si aucune borne n'est possible."""
        if self.input_cents_per_mtok is not None and self.output_cents_per_mtok is not None:
            out = max_output_tokens or self.max_output_tokens or 0
            return -(-(input_tokens * self.input_cents_per_mtok + out * self.output_cents_per_mtok) // 1_000_000)  # ceil
        return self.cost_per_call_cents

    def actual_cost_cents(self, usage: Optional[dict[str, Any]]) -> Optional[int]:
        """Coût constaté depuis l'usage réel (T8.5, F03) ; None si l'usage ou les tarifs sont
        absents (à réconcilier — le forfait cost_per_call_cents n'est JAMAIS présenté comme
        montant constaté)."""
        if usage is None or self.input_cents_per_mtok is None or self.output_cents_per_mtok is None:
            return None
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        return -(-(prompt_tokens * self.input_cents_per_mtok + completion_tokens * self.output_cents_per_mtok) // 1_000_000)

    async def complete(self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]) -> T:
        output, _usage = await self.complete_with_usage(role, prompt, input_data, response_model)
        return output

    async def complete_with_usage(
        self, role: str, prompt: str, input_data: dict[str, Any], response_model: Type[T]
    ) -> tuple[T, Optional[dict[str, Any]]]:
        payload = self._payload(prompt, input_data)
        status, _, body = await self._post(self.completions_url, payload)
        if status != 200:
            raise AIAdapterError(f"fournisseur {self.provider} : HTTP {status}", status=status)
        try:
            data = json.loads(body.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, UnicodeDecodeError) as exc:
            raise AIAdapterError(f"fournisseur {self.provider} : réponse illisible (pas de choices[0].message.content)", status=status) from exc
        # T8.5 / F03 : l'usage est conservé même si la sortie métier est ensuite rejetée
        self.last_usage = data.get("usage") if isinstance(data, dict) else None
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:  # TypeError : content null ou non str
            raise AIAdapterError(f"fournisseur {self.provider} : sortie non JSON (T8.6)", status=status) from exc
        # ValidationError propagée : le courtier rejette la sortie (T8.6, sortie_ia_invalide)
        return response_model.model_validate(parsed), self.last_usage

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
                 cost_per_call_cents: int = 5, input_cents_per_mtok: Optional[int] = 20,
                 output_cents_per_mtok: Optional[int] = 60, max_output_tokens: Optional[int] = 4096, **kw):
        super().__init__(
            provider="mistral",
            model=model,
            base_url=base_url,
            api_key=api_key,
            paid=True,
            cost_per_call_cents=cost_per_call_cents,
            input_cents_per_mtok=input_cents_per_mtok,
            output_cents_per_mtok=output_cents_per_mtok,
            max_output_tokens=max_output_tokens,
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
            input_cents_per_mtok=settings.mistral_input_cents_per_mtok,
            output_cents_per_mtok=settings.mistral_output_cents_per_mtok,
            max_output_tokens=settings.ai_max_output_tokens,
            timeout_seconds=settings.ai_timeout_seconds,
        )
        host = urlparse(settings.mistral_api_base).hostname
        if host:
            domains.add(host)
    provider = settings.ai_provider
    if provider not in adapters:
        # F05 : un fournisseur explicitement demandé (OSIA_AI_PROVIDER) mais indisponible est une
        # erreur de configuration explicite — JAMAIS un repli silencieux sur `simulated`, qui
        # produirait un plan vide valide confondu avec une investigation réelle sans résultat.
        if getattr(settings, "ai_provider_explicit", False):
            raise ConfigError(
                f"fournisseur IA demandé indisponible: {provider!r} "
                f"(disponibles: {', '.join(sorted(adapters))}) — compléter la configuration "
                "(clé API / endpoint local) ou retirer OSIA_AI_PROVIDER"
            )
        provider = "simulated"
    role_models = {role: provider for role in ("planning", "extraction", "synthesis")}
    return adapters, role_models, domains
