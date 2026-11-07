from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import time
from typing import Any, Optional

from .security.audit import _scrub  # même masquage des secrets que l'audit de sécurité (T5.9/T3.13)


class TechLog:
    """Journal TECHNIQUE structuré, DISTINCT de l'audit de sécurité (T3.13) et de l'historique
    métier en base (events/decisions/external_ops — jamais purgés automatiquement, D4 §6.1.A).

    - Fichier JSONL dédié `tech-YYYY-MM-DD.jsonl` dans log_dir, permissions 0600.
    - Entrées structurées : ts, level, component, event + identifiants de corrélation
      (investigation_id, branch_id, task_id, op_id), durée, erreur, détail — avec le même
      masquage des secrets que l'audit (aucune clé sensible, troncature à 256 caractères).
    - Rétention configurable (`tech_log_retention_days`, défaut 30 j), purge à l'écriture.
    """

    def __init__(self, log_dir: pathlib.Path, retention_days: int = 30):
        self.log_dir = pathlib.Path(log_dir)
        self.retention_days = retention_days

    @property
    def path(self) -> pathlib.Path:
        return self.log_dir / f"tech-{_dt.datetime.now(_dt.timezone.utc):%Y-%m-%d}.jsonl"

    def _ensure(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        os.chmod(self.path, 0o600)

    def log(
        self,
        component: str,
        event: str,
        *,
        level: str = "info",
        investigation_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        task_id: Optional[str] = None,
        op_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        """T3.13 : ne JAMAIS lever — un échec de journalisation ne doit pas faire échouer
        l'opération métier (source.query, ai.call, ...) qui la déclenche."""
        try:
            self._write(
                component, event,
                level=level,
                investigation_id=investigation_id,
                branch_id=branch_id,
                task_id=task_id,
                op_id=op_id,
                duration_ms=duration_ms,
                error=error,
                detail=detail,
            )
        except (OSError, TypeError, ValueError):
            pass

    def _write(
        self,
        component: str,
        event: str,
        *,
        level: str,
        investigation_id: Optional[str],
        branch_id: Optional[str],
        task_id: Optional[str],
        op_id: Optional[str],
        duration_ms: Optional[int],
        error: Optional[str],
        detail: Optional[dict[str, Any]],
    ) -> None:
        self._ensure()
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level,
            "component": component,
            "event": event,
        }
        for key, value in (
            ("investigation_id", investigation_id),
            ("branch_id", branch_id),
            ("task_id", task_id),
            ("op_id", op_id),
            ("duration_ms", duration_ms),
            ("error", _scrub(error) if error is not None else None),
        ):
            if value is not None:
                entry[key] = value
        if detail:
            entry["detail"] = _scrub(detail)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.purge()

    def _cutoff(self) -> float:
        return time.time() - self.retention_days * 86400

    def expired_count(self) -> int:
        """Prévisualisation (dry-run) : nombre d'entrées hors rétention, sans rien supprimer."""
        if self.retention_days <= 0 or not self.log_dir.exists():
            return 0
        cutoff = self._cutoff()
        count = 0
        for path in self.log_dir.glob("tech-*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    ts = json.loads(line)["ts"]
                    t = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
                if t < cutoff:
                    count += 1
        return count

    def purge(self) -> int:
        """Purge des entrées hors rétention. Retourne le nombre d'ENTRÉES supprimées
        (cohérent avec SecurityAudit.purge, exposé comme ``removed_entries`` par l'API/CLI)."""
        if self.retention_days <= 0 or not self.log_dir.exists():
            return 0
        cutoff = self._cutoff()
        removed = 0
        for path in sorted(self.log_dir.glob("tech-*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                continue
            kept: list[str] = []
            for line in lines:
                try:
                    ts = json.loads(line)["ts"]
                    t = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue  # ligne illisible : écartée (jamais de secret supposé présent)
                if t >= cutoff:
                    kept.append(line)
            expired = len(lines) - len(kept)
            removed += expired
            if expired:
                if kept:
                    tmp = path.with_suffix(".jsonl.tmp")
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write("\n".join(kept) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp, path)
                else:
                    path.unlink()
        return removed

    def read(self, limit: int = 100) -> list[dict]:
        if not self.log_dir.exists():
            return []
        entries: list[dict] = []
        for path in sorted(self.log_dir.glob("tech-*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries[-limit:]

    def stats(self) -> dict:
        """Taille et nombre d'entrées du journal technique (pour la prévisualisation des purges)."""
        files = sorted(self.log_dir.glob("tech-*.jsonl")) if self.log_dir.exists() else []
        total_bytes = sum(f.stat().st_size for f in files)
        return {"files": len(files), "bytes": total_bytes, "retention_days": self.retention_days}
