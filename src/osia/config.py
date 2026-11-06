from __future__ import annotations

import hashlib
import os
import pathlib
from dataclasses import dataclass, field

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
        for restricted in (self.config_dir, self.data_dir):
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
    paid_calls_enabled: bool = False
    global_monthly_cap_cents: int = 500
    timezone: str = "UTC"
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
        return settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
