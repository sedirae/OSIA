from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import re
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


def _bin_major(binary: str) -> Optional[int]:
    """Version majeure d'un binaire PostgreSQL (ex. 'pg_dump (PostgreSQL) 16.2' -> 16)."""
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"(\d+)\.", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _pg_bin(name: str, server_major: Optional[int] = None) -> str:
    """Binaire PostgreSQL compatible avec le serveur cible (audit F14).

    Ordre : binaire dont la version majeure correspond au serveur connecté (pgserver embarqué
    en tests/CI, où un PostgreSQL système d'une autre version majeure peut être dans le PATH),
    puis PATH (installation gérée, CON-01), puis embarqué en dernier repli. Mélanger pg_dump et
    pg_restore de versions majeures différentes est la cause d'échec pg_restore constatée en CI."""
    candidates: list[str] = []
    try:
        import pgserver

        embedded = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin" / name
        if embedded.exists():
            candidates.append(str(embedded))
    except ImportError:
        pass
    found = shutil.which(name)
    if found:
        candidates.append(found)
    if not candidates:
        raise BackupError(f"binaire {name} introuvable (PostgreSQL requis, CON-01)")
    if server_major is not None:
        for candidate in candidates:
            if _bin_major(candidate) == server_major:
                return candidate
    return found if found else candidates[0]


def _scrub(text: str, secrets: list[str]) -> str:
    """Nettoie un message d'erreur des secrets éventuels avant journalisation (T5.9)."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


async def _run_pg(args: list[str], env: dict[str, str], secrets: list[str]) -> None:
    """Exécute un binaire PostgreSQL SANS bloquer la boucle d'événements (audit F14) et en
    levant une BackupError dont le stderr est nettoyé des secrets (diagnostic CI exploitable)."""
    try:
        await asyncio.to_thread(
            subprocess.run, args, check=True, env=env, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = _scrub((exc.stderr or b"").decode("utf-8", errors="replace"), secrets)
        raise BackupError(f"{pathlib.Path(args[0]).name} a échoué (rc={exc.returncode}): {stderr.strip() or exc}") from exc


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

    async def _server_major(self) -> Optional[int]:
        """Version majeure du serveur connecté (pour choisir des binaires compatibles, F14)."""
        try:
            version = await self.pool.fetchval("SHOW server_version")
            return int(str(version).split(".")[0]) if version else None
        except Exception:
            return None

    async def _db_is_empty(self, dsn: Optional[str] = None) -> bool:
        """Vrai si la base (courante, ou `dsn` cible) ne contient aucune donnée métier."""
        if dsn and dsn != self.settings.db_dsn:
            try:
                conn = await asyncpg.connect(dsn)
            except Exception as exc:
                raise BackupError(f"DSN cible injoignable: {exc}") from exc
            try:
                row = await conn.fetchrow(
                    "SELECT (SELECT COUNT(*) FROM investigations) + (SELECT COUNT(*) FROM entities) + (SELECT COUNT(*) FROM proof_files) AS n"
                )
                return int(row["n"]) == 0 if row else True
            except Exception:
                return True  # schéma absent (base vierge) = vide
            finally:
                await conn.close()
        row = await self.pool.fetchrow(
            "SELECT (SELECT COUNT(*) FROM investigations) + (SELECT COUNT(*) FROM entities) + (SELECT COUNT(*) FROM proof_files) AS n"
        )
        return int(row["n"]) == 0 if row else True

    async def create(self, dest_dir: Optional[pathlib.Path] = None, kind: str = "manual") -> dict[str, Any]:
        result, journal = await self._create_files(dest_dir=dest_dir, kind=kind)
        await self._journal(journal)
        await self.bus.emit(type="backup.created", payload={"backup_id": journal["id"], "dest_dir": journal["dest_dir"], "kind": journal["kind"], "proof_files": journal["proof_files_count"]})
        return result

    # Fichiers de configuration exclus d'une sauvegarde : secrets (jeton, clés, coffre) —
    # leurs NOMS figurent dans le manifeste, jamais leur contenu (T5.9, audit F14).
    _SECRET_NAME = re.compile(r"(secret|token|passphrase|password|\.key$|\.pem$|\.env)", re.IGNORECASE)

    def _config_inventory(self, dest: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
        """Copie les fichiers de configuration NON secrets dans dest/config et retourne
        (fichiers inclus avec empreintes, noms des fichiers secrets exclus)."""
        included: list[dict[str, Any]] = []
        excluded: list[str] = []
        src = self.paths.config_dir
        if not src.exists():
            return included, excluded
        cfg_dest = dest / "config"
        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(src))
            if self._SECRET_NAME.search(p.name):
                excluded.append(rel)
                continue
            target = cfg_dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            included.append({"path": f"config/{rel}", "sha256": _sha256_file(target), "size_bytes": target.stat().st_size})
        return included, excluded

    async def _create_files(self, dest_dir: Optional[pathlib.Path], kind: str, dsn: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        if kind not in ("manual", "pre_restore"):
            raise BackupError(f"kind inconnu: {kind}")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        base = pathlib.Path(dest_dir) if dest_dir else self.paths.backup_dir / f"{ts}_osia-backup"
        # F14 : jamais de collision de dossier (identifiant à la microseconde + suffixe)
        dest = base
        n = 1
        while dest.exists():
            n += 1
            dest = base.parent / f"{base.name}-{n}"
        dest.mkdir(parents=True, exist_ok=False)
        effective_dsn = dsn or self.settings.db_dsn or ""
        parts = _dsn_parts(effective_dsn)
        server_major = await self._server_major() if not dsn or dsn == self.settings.db_dsn else None
        if server_major is None and dsn:
            try:
                conn = await asyncpg.connect(dsn)
                version = await conn.fetchval("SHOW server_version")
                server_major = int(str(version).split(".")[0]) if version else None
                await conn.close()
            except Exception:
                server_major = None
        dump_path = dest / "db.dump"
        env = dict(os.environ)
        if parts["password"]:
            env["PGPASSWORD"] = parts["password"]
        secrets = [parts["password"]]
        base_args = ["-h", parts["host"], "-p", parts["port"], "-U", parts["user"]]
        try:
            await _run_pg([_pg_bin("pg_dump", server_major), *base_args, "-Fc", "-f", str(dump_path), parts["dbname"]], env, secrets)
            dump_format = "custom"
        except BackupError:
            dump_path = dest / "db.sql"
            await _run_pg([_pg_bin("pg_dump", server_major), *base_args, "-Fp", "--no-owner", "-f", str(dump_path), parts["dbname"]], env, secrets)
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
        config_files, excluded_secrets = await asyncio.to_thread(self._config_inventory, dest)
        if dsn and dsn != self.settings.db_dsn:
            # sauvegarde pre-restore d'une base CIBLE : version de schéma de la cible
            try:
                conn = await asyncpg.connect(dsn)
                row = await conn.fetchrow("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations")
                schema_version = int(row["v"]) if row else 0
                await conn.close()
            except Exception:
                schema_version = 0
        else:
            schema_version = await self._schema_version()
        manifest = {
            "format": "osia-backup",
            "format_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "schema_version": schema_version,
            "db_dump": {"file": dump_path.name, "format": dump_format, "sha256": _sha256_file(dump_path), "size_bytes": dump_path.stat().st_size},
            "proof_files": proof_files,
            "config_files": config_files,
            "excluded_secret_files": excluded_secrets,
            "counts": {"proof_files": len(proof_files), "config_files": len(config_files)},
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
                    server_major = await self._server_major()
                    await _run_pg([_pg_bin("pg_restore", server_major), "--list", str(dump_path)], dict(os.environ), [])
                except BackupError as exc:
                    errors.append(f"pg_restore --list en échec: {exc}")
            for entry in manifest.get("proof_files", []):
                p = dest / entry["path"]
                if not p.exists() or _sha256_file(p) != entry["sha256"]:
                    errors.append(f"fichier de preuve absent ou altere: {entry['path']}")
            for entry in manifest.get("config_files", []):
                p = dest / entry["path"]
                if not p.exists() or _sha256_file(p) != entry["sha256"]:
                    errors.append(f"fichier de configuration absent ou altere: {entry['path']}")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE backups SET verified_at = now(), verify_errors = $2::jsonb WHERE id = $1",
                backup_id, json.dumps(errors),
            )
        await self.bus.emit(type="backup.verified", payload={"backup_id": backup_id, "errors": errors})
        return {"backup_id": backup_id, "verified": not errors, "errors": errors}

    async def restore(
        self,
        backup_id: str,
        *,
        confirm: bool = False,
        target_dsn: Optional[str] = None,
        target_proofs_dir: Optional[pathlib.Path] = None,
    ) -> dict[str, Any]:
        """Restauration supervisée (CLI, D5.7.2, audit F14) : vérification d'abord, sauvegarde
        préalable automatique si la base CIBLE est non vide, confirmation explicite requise.

        - `target_dsn=None` : restauration EN PLACE de la base courante — les preuves courantes
          sont remplacées (après sauvegarde préalable).
        - `target_dsn` fourni : restauration vers une base externe (staging/maintenance) —
          `target_proofs_dir` EXPLICITE requis ; les preuves de l'installation courante ne sont
          JAMAIS touchées, et la sauvegarde préalable porte sur la base cible."""
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
        in_place = target_dsn is None
        if not in_place and target_proofs_dir is None:
            raise BackupError("restauration vers une base externe : --target-proofs-dir explicite requis (les preuves courantes ne sont jamais modifiées)")
        pre_restore = None
        pre_restore_journal = None
        # F14 : la sauvegarde préalable s'applique à la base CIBLE (courante ou externe)
        if not await self._db_is_empty(dsn):
            pre_restore, pre_restore_journal = await self._create_files(dest_dir=None, kind="pre_restore", dsn=dsn)
        parts = _dsn_parts(dsn)
        env = dict(os.environ)
        if parts["password"]:
            env["PGPASSWORD"] = parts["password"]
        secrets = [parts["password"]]
        base_args = ["-h", parts["host"], "-p", parts["port"], "-U", parts["user"]]
        dump_path = dest / manifest["db_dump"]["file"]
        server_major = await self._server_major() if in_place else None
        if server_major is None:
            try:
                conn = await asyncpg.connect(dsn)
                version = await conn.fetchval("SHOW server_version")
                server_major = int(str(version).split(".")[0]) if version else None
                await conn.close()
            except Exception:
                server_major = None
        try:
            if manifest["db_dump"]["format"] == "custom":
                await _run_pg(
                    [_pg_bin("pg_restore", server_major), *base_args, "--clean", "--if-exists", "-d", parts["dbname"], str(dump_path)],
                    env, secrets,
                )
            else:
                await _run_pg(
                    [_pg_bin("psql", server_major), *base_args, "-d", parts["dbname"], "-v", "ON_ERROR_STOP=1", "-f", str(dump_path)],
                    env, secrets,
                )
            proofs_src = dest / "proofs"
            if in_place:
                proofs_dst = self.paths.proofs_dir / "sha256"
                if proofs_dst.exists():
                    shutil.rmtree(proofs_dst)
                if proofs_src.exists():
                    shutil.copytree(proofs_src, proofs_dst)
            else:
                # F14 : cible externe -> preuves restaurées dans le dossier explicite, jamais chez soi
                proofs_dst = pathlib.Path(target_proofs_dir) / "sha256"
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
        await self.bus.emit(type="backup.restored", payload={"backup_id": backup_id, "pre_restore": pre_restore["id"] if pre_restore else None, "target_dsn": target_dsn})
        return {
            "backup_id": backup_id,
            "restored": True,
            "pre_restore_backup_id": pre_restore["id"] if pre_restore else None,
            "target_dsn": target_dsn,
            "target_proofs_dir": str(target_proofs_dir) if target_proofs_dir else None,
        }


__all__ = ["BackupService", "BackupError"]
