from __future__ import annotations

import hashlib
import os
import pathlib
from dataclasses import dataclass, field


class ConfigError(Exception):
    """Configuration invalide pour le mode demandé (T1/T5.7 : pas d'exposition distante implicite)."""


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_host(host: str) -> bool:
    return host in _LOCAL_HOSTS


def secure_write(path: pathlib.Path, data: bytes | str) -> None:
    """Écrit un fichier sensible (jeton, certificat) avec les permissions 0600 dès la création."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)  # resserre aussi un fichier pré-existant trop permissif
        handle.write(data.encode() if isinstance(data, str) else data)
        handle.flush()
        os.fsync(handle.fileno())


_ENV_PATHS = {
    "config_dir": "OSIA_CONFIG_DIR",
    "data_dir": "OSIA_DATA_DIR",
    "cache_dir": "OSIA_CACHE_DIR",
    "log_dir": "OSIA_LOG_DIR",
    "backup_dir": "OSIA_BACKUP_DIR",
}


@dataclass
class Paths:
    config_dir: pathlib.Path
    data_dir: pathlib.Path
    cache_dir: pathlib.Path
    log_dir: pathlib.Path
    backup_dir: pathlib.Path

    @classmethod
    def from_env(cls, mode: str = "desktop") -> "Paths":
        home = pathlib.Path.home()
        if mode == "server":
            defaults = {
                "config_dir": "/etc/osia",
                "data_dir": "/var/lib/osia",
                "cache_dir": "/var/cache/osia",
                "log_dir": "/var/log/osia",
                "backup_dir": "/var/backups/osia",
            }
        else:
            defaults = {
                "config_dir": home / ".config" / "osia",
                "data_dir": home / ".local" / "share" / "osia",
                "cache_dir": home / ".cache" / "osia",
                "log_dir": home / ".local" / "state" / "osia" / "logs",
                "backup_dir": home / ".local" / "share" / "osia" / "backups",
            }
        values = {}
        for key, env in _ENV_PATHS.items():
            raw = os.environ.get(env)
            values[key] = pathlib.Path(raw) if raw else pathlib.Path(defaults[key])
        return cls(**values)

    @property
    def proofs_dir(self) -> pathlib.Path:
        return self.data_dir / "proofs"

    @property
    def incoming_dir(self) -> pathlib.Path:
        return self.proofs_dir / "incoming"

    def ensure(self) -> None:
        for directory in (
            self.config_dir,
            self.data_dir,
            self.cache_dir,
            self.log_dir,
            self.backup_dir,
            self.incoming_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        # CON-05 / D6 : répertoires sensibles en 0700 (config, données, logs, sauvegardes, preuves).
        for restricted in (self.config_dir, self.data_dir, self.log_dir, self.backup_dir, self.proofs_dir):
            try:
                restricted.chmod(0o700)
            except PermissionError:
                pass


@dataclass
class Settings:
    mode: str = "desktop"
    db_dsn: str | None = None
    listen_host: str = "127.0.0.1"
    listen_port: int = 8471
    auth_token_hash: str | None = None
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    tls_autogen: bool = False
    session_ttl_hours: int = 8
    audit_retention_days: int = 90
    tech_log_retention_days: int = 30  # CON-18 / T3.13 : journal technique, rétention distincte
    net_allow_domains: list[str] = field(default_factory=list)
    net_deny_domains: list[str] = field(default_factory=list)
    net_max_bytes: int = 10 * 1024 * 1024
    secrets_persist: bool = True
    paid_calls_enabled: bool = False
    global_monthly_cap_cents: int = 500
    timezone: str = "UTC"
    # CON-11 / V1.3 : fournisseurs IA (simulé par défaut — aucun appel payant sans config explicite)
    ai_provider: str = "simulated"
    ai_local_base_url: str | None = None
    ai_local_model: str = "ministral-3-8b"
    ai_timeout_seconds: int = 60  # V1.4 : 60 s max par appel IA
    mistral_api_base: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-small-2603"
    mistral_cost_cents: int = 5  # borne estimée par appel (T8.4 : réservation avant l'appel)
    paths: Paths = field(default_factory=Paths.from_env)

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(paths=Paths.from_env(os.environ.get("OSIA_MODE", "desktop")))
        settings.mode = os.environ.get("OSIA_MODE", settings.mode)
        settings.db_dsn = os.environ.get("OSIA_DB_DSN")
        settings.listen_host = os.environ.get("OSIA_LISTEN_HOST", settings.listen_host)
        settings.listen_port = int(os.environ.get("OSIA_LISTEN_PORT", settings.listen_port))
        token = os.environ.get("OSIA_AUTH_TOKEN")
        if token:
            settings.auth_token_hash = hashlib.sha256(token.encode()).hexdigest()
        settings.tls_certfile = os.environ.get("OSIA_TLS_CERTFILE")
        settings.tls_keyfile = os.environ.get("OSIA_TLS_KEYFILE")
        autogen = os.environ.get("OSIA_TLS_AUTOGEN", "").strip().lower()
        if autogen:
            settings.tls_autogen = autogen in ("1", "true", "yes", "on")
        ttl = os.environ.get("OSIA_SESSION_TTL_HOURS")
        if ttl:
            settings.session_ttl_hours = int(ttl)
        retention = os.environ.get("OSIA_AUDIT_RETENTION_DAYS")
        if retention:
            settings.audit_retention_days = int(retention)
        tretention = os.environ.get("OSIA_TECH_LOG_RETENTION_DAYS")
        if tretention:
            settings.tech_log_retention_days = int(tretention)
        allow = os.environ.get("OSIA_NET_ALLOW_DOMAINS", "")
        if allow:
            settings.net_allow_domains = [d.strip().lower() for d in allow.split(",") if d.strip()]
        deny = os.environ.get("OSIA_NET_DENY_DOMAINS", "")
        if deny:
            settings.net_deny_domains = [d.strip().lower() for d in deny.split(",") if d.strip()]
        maxb = os.environ.get("OSIA_NET_MAX_BYTES")
        if maxb:
            settings.net_max_bytes = int(maxb)
        persist = os.environ.get("OSIA_SECRETS_PERSIST", "1").strip().lower()
        settings.secrets_persist = persist in ("1", "true", "yes", "on")
        paid = os.environ.get("OSIA_PAID_CALLS_ENABLED", "").strip().lower()
        if paid:
            settings.paid_calls_enabled = paid in ("1", "true", "yes", "on")
        cap = os.environ.get("OSIA_GLOBAL_MONTHLY_CAP_CENTS")
        if cap:
            settings.global_monthly_cap_cents = int(cap)
        settings.ai_provider = os.environ.get("OSIA_AI_PROVIDER", settings.ai_provider)
        settings.ai_local_base_url = os.environ.get("OSIA_AI_LOCAL_BASE_URL") or None
        settings.ai_local_model = os.environ.get("OSIA_AI_LOCAL_MODEL", settings.ai_local_model)
        ait = os.environ.get("OSIA_AI_TIMEOUT_SECONDS")
        if ait:
            settings.ai_timeout_seconds = int(ait)
        settings.mistral_api_base = os.environ.get("OSIA_MISTRAL_API_BASE", settings.mistral_api_base)
        settings.mistral_model = os.environ.get("OSIA_MISTRAL_MODEL", settings.mistral_model)
        mcost = os.environ.get("OSIA_MISTRAL_COST_CENTS")
        if mcost:
            settings.mistral_cost_cents = int(mcost)
        return settings

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_certfile and self.tls_keyfile)

    def validate_runtime(self) -> None:
        """CON-05 (T1/T5.7) : aucune exposition distante implicite.

        - mode desktop : écoute locale uniquement (127.0.0.1/localhost/::1) ;
        - mode serveur exposé (host non local) : HTTPS obligatoire (certificats fournis ou autogénérés).
        """
        if self.mode == "desktop" and not is_local_host(self.listen_host):
            raise ConfigError(
                "mode desktop : écoute locale uniquement (OSIA_LISTEN_HOST=127.0.0.1) — "
                "aucune exposition distante implicite (T1/T5.7)"
            )
        if self.mode == "server" and not is_local_host(self.listen_host) and not (self.tls_enabled or self.tls_autogen):
            raise ConfigError(
                "mode serveur exposé sur un host non local : HTTPS obligatoire (T5.7) — "
                "fournir OSIA_TLS_CERTFILE/OSIA_TLS_KEYFILE ou activer OSIA_TLS_AUTOGEN=1"
            )
