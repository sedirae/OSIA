from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
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

# Dans une chaîne libre (message d'erreur, détail), masque aussi les motifs "clé=valeur" ou
# "clé: valeur" pour les clés sensibles (ex. "échec token=abcdef" -> "échec token=***").
_SENSITIVE_INLINE = re.compile(
    r"\b(" + "|".join(sorted(_SENSITIVE_KEYS, key=len, reverse=True)) + r")\b(\s*[=:]\s*)(\S+)",
    re.IGNORECASE,
)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        masked = _SENSITIVE_INLINE.sub(lambda m: m.group(1) + m.group(2) + "***", value)
        if len(masked) > 256:
            return masked[:256] + "…"
        return masked
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

    def _cutoff(self) -> float:
        return time.time() - self.retention_days * 86400

    def _entries(self) -> list[str]:
        try:
            return self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

    def expired_count(self) -> int:
        """CON-18 : prévisualisation (dry-run) du nombre d'entrées hors rétention."""
        if self.retention_days <= 0:
            return 0
        cutoff = self._cutoff()
        count = 0
        for line in self._entries():
            try:
                ts = json.loads(line)["ts"]
                t = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if t < cutoff:
                count += 1
        return count

    def purge(self) -> int:
        """CON-18 : purge manuelle supervisée — supprime les entrées hors rétention.
        Retourne le nombre d'entrées supprimées (0 = rien à purger, pas de réécriture)."""
        if self.retention_days <= 0:
            return 0
        cutoff = self._cutoff()
        lines = self._entries()
        kept: list[str] = []
        for line in lines:
            try:
                ts = json.loads(line)["ts"]
                t = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if t >= cutoff:
                kept.append(line)
        removed = len(lines) - len(kept)
        if removed == 0:
            return 0
        tmp = self.path.with_suffix(".jsonl.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(kept) + ("\n" if kept else ""))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        return removed

    def _purge(self) -> None:
        self.purge()

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
