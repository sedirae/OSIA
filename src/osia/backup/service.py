from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..config import Paths, Settings
from ..events import EventBus
from ..ids import new_id
from ..store.repo import Repo


class BackupError(Exception):
    pass


def _pg_bin(name: str) -> str:
    """Binaire PostgreSQL : PATH d'abord (installation geree, CON-01), pgserver embarque sinon (tests)."""
    found = shutil.which(name)
    if found:
        return found
    try:
        import pgserver

        candidate = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin" / name
        if candidate.exists():
            return str(candidate)
    except ImportError:
        pass
    raise BackupError(f"binaire {name} introuvable (PostgreSQL requis, CON-01)")


def _dsn_parts(dsn: str) -> dict[str, str]:
    """Parse un DSN postgres:// (TCP ou socket Unix : host en query param, ex. pgserver)."""
    parsed = urllib.parse.urlparse(dsn)
    query = urllib.parse.parse_qs(parsed.query)
    host = (query.get("host") or [None])[0] or parsed.hostname or "127.0.0.1"
    port = (query.get("port") or [None])[0] or (str(parsed.port) if parsed.port else "5432")
    return {
        "host": host,
        "port": str(port),
        "user": urllib.parse.unquote(parsed.username or "postgres"),
        "password": urllib.parse.unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/") or (query.get("dbname") or ["postgres"])[0],
    }


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupService:
    """Sauvegarde technique manuelle coherente a chaud (T2.6, CON-16, V1.1) + restauration supervisee.

    La sauvegarde couvre la base (pg_dump, snapshot coherente interne PostgreSQL) ET les
    fichiers de preuves, avec manifeste et empreintes SHA-256 ; le moteur n'est pas arrete.
    Elle est distincte de l'archive portable .osia (T7.9). La restauration est une operation
    destructive : confirmation explicite requise, sauvegarde prealable automatique si la base
    est non vide (D5.7.2)."""

    def __init__(self, pool: asyncpg.Pool, repo: Repo, bus: EventBus, paths: Paths, settings: Settings):
        self.pool = pool
        self.repo = repo
        self.bus = bus
        self.paths = paths
        self.settings = settings

    async def _schema_version(self) -> int:
        row = await self.pool.fetchrow("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations")
        return int(row["v"]) if row else 0

    async def _db_is_empty(self) -> bool:
        row = await self.pool.fetchrow(
            "SELECT (SELECT COUNT(*) FROM investigations) + (SELECT COUNT(*) FROM entities) + (SELECT COUNT(*) FROM proof_files) AS n"
        )
        return int(row["n"]) == 0 if row else True

    async def create(self, dest_dir: Optional[pathlib.Path] = None, kind: str = "manual") -> dict[str, Any]:
        result, journal = await self._create_files(dest_dir=dest_dir, kind=kind)
        await self._journal(journal)
        await self.bus.emit(type="backup.created", payload={"backup_id": journal["id"], "dest_dir": journal["dest_dir"], "kind": journal["kind"], "proof_files": journal["proof_files_count"]})
        return result

    async def _create_files(self, dest_dir: Optional[pathlib.Path], kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if kind not in ("manual", "pre_restore"):
            raise BackupError(f"kind inconnu: {kind}")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = pathlib.Path(dest_dir) if dest_dir else self.paths.backup_dir / f"{ts}_osia-backup"
        dest.mkdir(parents=True, exist_ok=True)
        parts = _dsn_parts(self.settings.db_dsn or "")
        dump_path = dest / "db.dump"
        env = dict(os.environ)
        if parts["password"]:
            env["PGPASSWORD"] = parts["password"]
        base_args = ["-h", parts["host"], "-p", parts["port"], "-U", parts["user"]]
        try:
            subprocess.run(
                [_pg_bin("pg_dump"), *base_args, "-Fc", "-f", str(dump_path), parts["dbname"]],
                check=True, env=env, capture_output=True,
            )
            dump_format = "custom"
        except (subprocess.CalledProcessError, BackupError):
            dump_path = dest / "db.sql"
            subprocess.run(
                [_pg_bin("pg_dump"), *base_args, "-Fp", "--no-owner", "-f", str(dump_path), parts["dbname"]],
                check=True, env=env, capture_output=True,
            )
            dump_format = "plain"
        proofs_src = self.paths.proofs_dir / "sha256"
        proofs_dest = dest / "proofs"
        proof_files: list[dict[str, Any]] = []
        if proofs_src.exists():
            shutil.copytree(proofs_src, proofs_dest, dirs_exist_ok=True)
            for p in sorted(proofs_dest.rglob("*")):
                if p.is_file():
                    rel = str(p.relative_to(dest))
                    proof_files.append({"path": rel, "sha256": _sha256_file(p), "size_bytes": p.stat().st_size})
        schema_version = await self._schema_version()
        manifest = {
            "format": "osia-backup",
            "format_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "schema_version": schema_version,
            "db_dump": {"file": dump_path.name, "format": dump_format, "sha256": _sha256_file(dump_path), "size_bytes": dump_path.stat().st_size},
            "proof_files": proof_files,
            "counts": {"proof_files": len(proof_files)},
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        (dest / "manifest.json").write_bytes(manifest_bytes)
        size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
        backup_id = new_id("bak")
        journal = {
            "id": backup_id, "kind": kind, "dest_dir": str(dest),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "db_dump_sha256": manifest["db_dump"]["sha256"], "schema_version": schema_version,
            "proof_files_count": len(proof_files), "size_bytes": size,
        }
        result = {"id": backup_id, "dest_dir": str(dest), "manifest": manifest, "size_bytes": size}
        return result, journal

    async def _journal(self, journal: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO backups (id, kind, dest_dir, manifest_sha256, db_dump_sha256, schema_version, proof_files_count, size_bytes) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                journal["id"], journal["kind"], journal["dest_dir"], journal["manifest_sha256"],
                journal["db_dump_sha256"], journal["schema_version"], journal["proof_files_count"], journal["size_bytes"],
            )

    async def list_backups(self) -> list[dict[str, Any]]:
        return await self.repo._fetch("SELECT * FROM backups ORDER BY created_at DESC")

    async def get_backup(self, backup_id: str) -> Optional[dict[str, Any]]:
        return await self.repo._fetchrow("SELECT * FROM backups WHERE id = $1", backup_id)

    def _load_manifest(self, dest: pathlib.Path) -> dict[str, Any]:
        path = dest / "manifest.json"
        if not path.exists():
            raise BackupError(f"manifeste absent: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    async def verify(self, backup_id: str) -> dict[str, Any]:
        row = await self.get_backup(backup_id)
        if row is None:
            raise BackupError(f"sauvegarde inconnue: {backup_id}")
        dest = pathlib.Path(row["dest_dir"])
        errors: list[str] = []
        try:
            manifest = self._load_manifest(dest)
        except (BackupError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            manifest = None
        if manifest:
            dump_path = dest / manifest["db_dump"]["file"]
            if not dump_path.exists() or _sha256_file(dump_path) != manifest["db_dump"]["sha256"]:
                errors.append("dump de base absent ou empreinte invalide")
            elif manifest["db_dump"]["format"] == "custom":
                try:
                    subprocess.run([_pg_bin("pg_restore"), "--list", str(dump_path)], check=True, capture_output=True)
                except (subprocess.CalledProcessError, BackupError) as exc:
                    errors.append(f"pg_restore --list en echec: {exc}")
            for entry in manifest.get("proof_files", []):
                p = dest / entry["path"]
                if not p.exists() or _sha256_file(p) != entry["sha256"]:
                    errors.append(f"fichier de preuve absent ou altere: {entry['path']}")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE backups SET verified_at = now(), verify_errors = $2::jsonb WHERE id = $1",
                backup_id, json.dumps(errors),
            )
        await self.bus.emit(type="backup.verified", payload={"backup_id": backup_id, "errors": errors})
        return {"backup_id": backup_id, "verified": not errors, "errors": errors}

    async def restore(self, backup_id: str, *, confirm: bool = False, target_dsn: Optional[str] = None) -> dict[str, Any]:
        """Restauration supervisee (CLI, D5.7.2) : verification d'abord, sauvegarde prealable
        automatique si la base cible est non vide, confirmation explicite requise."""
        if not confirm:
            raise BackupError("restauration destructive : confirmation explicite requise (confirm=True / --yes)")
        row = await self.get_backup(backup_id)
        if row is None:
            raise BackupError(f"sauvegarde inconnue: {backup_id}")
        dest = pathlib.Path(row["dest_dir"])
        verification = await self.verify(backup_id)
        if not verification["verified"]:
            raise BackupError("restauration refusee : sauvegarde non verifiee: " + "; ".join(verification["errors"]))
        manifest = self._load_manifest(dest)
        dsn = target_dsn or self.settings.db_dsn
        if not dsn:
            raise BackupError("DSN cible requis pour la restauration")
        pre_restore = None
        pre_restore_journal = None
        if target_dsn is None and not await self._db_is_empty():
            pre_restore, pre_restore_journal = await self._create_files(dest_dir=None, kind="pre_restore")
        parts = _dsn_parts(dsn)
        env = dict(os.environ)
        if parts["password"]:
            env["PGPASSWORD"] = parts["password"]
        base_args = ["-h", parts["host"], "-p", parts["port"], "-U", parts["user"]]
        dump_path = dest / manifest["db_dump"]["file"]
        try:
            if manifest["db_dump"]["format"] == "custom":
                subprocess.run(
                    [_pg_bin("pg_restore"), *base_args, "--clean", "--if-exists", "-d", parts["dbname"], str(dump_path)],
                    check=True, env=env, capture_output=True,
                )
            else:
                subprocess.run(
                    [_pg_bin("psql"), *base_args, "-d", parts["dbname"], "-v", "ON_ERROR_STOP=1", "-f", str(dump_path)],
                    check=True, env=env, capture_output=True,
                )
            proofs_src = dest / "proofs"
            proofs_dst = self.paths.proofs_dir / "sha256"
            if proofs_dst.exists():
                shutil.rmtree(proofs_dst)
            if proofs_src.exists():
                shutil.copytree(proofs_src, proofs_dst)
        except BaseException:
            # La sauvegarde prealable existe sur disque : la journaliser au mieux pour
            # ne pas laisser une sauvegarde orpheline si la restauration echoue.
            if pre_restore_journal is not None:
                try:
                    await self._journal(pre_restore_journal)
                except Exception:
                    pass
            raise
        if pre_restore_journal is not None:
            await self._journal(pre_restore_journal)
            await self.bus.emit(type="backup.created", payload={"backup_id": pre_restore_journal["id"], "dest_dir": pre_restore_journal["dest_dir"], "kind": "pre_restore", "proof_files": pre_restore_journal["proof_files_count"]})
        await self.bus.emit(type="backup.restored", payload={"backup_id": backup_id, "pre_restore": pre_restore["id"] if pre_restore else None})
        return {"backup_id": backup_id, "restored": True, "pre_restore_backup_id": pre_restore["id"] if pre_restore else None}


__all__ = ["BackupService", "BackupError"]
