from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import time
from typing import Any, Optional

# Clés jamais journalisées dans l'audit de sécurité (T5.9 : pas de secrets).
_SENSITIVE_KEYS = {
    "token",
    "auth_token",
    "authorization",
    "passphrase",
    "secret",
    "password",
    "key",
    "session_token",
    "api_key",
}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and len(value) > 256:
        return value[:256] + "…"
    return value


class SecurityAudit:
    """Journal d'audit de sécurité DISTINCT de la télémétrie technique (T5.9).

    Fichier JSONL dédié dans log_dir, permissions 0600, rétention configurable
    (OSIA_AUDIT_RETENTION_DAYS, défaut 90 jours), aucun secret journalisé.
    """

    def __init__(self, log_dir: pathlib.Path, retention_days: int = 90):
        self.path = pathlib.Path(log_dir) / "security-audit.jsonl"
        self.retention_days = retention_days

    def _ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        os.chmod(self.path, 0o600)

    def log(
        self,
        action: str,
        outcome: str = "success",
        *,
        detail: Optional[dict[str, Any]] = None,
        client: Optional[str] = None,
    ) -> None:
        self._ensure()
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "outcome": outcome,
            "client": client,
            "detail": _scrub(detail or {}),
        }
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._purge()

    def _purge(self) -> None:
        if self.retention_days <= 0:
            return
        cutoff = time.time() - self.retention_days * 86400
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        kept: list[str] = []
        for line in lines:
            try:
                ts = json.loads(line)["ts"]
                t = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if t >= cutoff:
                kept.append(line)
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def read(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
