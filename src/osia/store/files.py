from __future__ import annotations

import hashlib
import os
import pathlib
from dataclasses import dataclass

import asyncpg

from ..config import Paths
from ..ids import new_id
from .repo import Repo


@dataclass
class IntegrityReport:
    orphan_files: list[str]
    missing_files: list[str]


class FileStore:
    """Stockage des preuves : déduplication SHA-256 et protocole de cohérence base/fichiers (CON-02 §3)."""

    def __init__(self, pool: asyncpg.Pool, paths: Paths):
        self.pool = pool
        self.paths = paths
        self.repo = Repo(pool)

    def _content_path(self, sha256: str) -> pathlib.Path:
        return self.paths.proofs_dir / "sha256" / sha256[:2] / sha256[2:4] / sha256

    async def store_proof(
        self,
        *,
        investigation_id: str,
        content: bytes,
        source_url: str | None = None,
        media_type: str | None = None,
        label: str | None = None,
    ) -> dict:
        """Protocole en 4 phases : (1) .part fsync, (2) déplacement atomique + SHA-256,
        (3) transaction SQL proof_files + proof_refs, (4) commit."""
        sha256 = hashlib.sha256(content).hexdigest()
        incoming = self.paths.incoming_dir / f"{sha256}.part"
        final = self._content_path(sha256)
        self.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        with open(incoming, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if not final.exists():
            os.rename(incoming, final)
        else:
            incoming.unlink(missing_ok=True)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO proof_files (sha256, path, size_bytes) VALUES ($1, $2, $3) "
                    "ON CONFLICT (sha256) DO NOTHING",
                    sha256,
                    str(final.relative_to(self.paths.data_dir)),
                    len(content),
                )
                ref = await conn.fetchrow(
                    "INSERT INTO proof_refs (id, investigation_id, proof_sha256, source_url, media_type, label) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                    new_id("proof"),
                    investigation_id,
                    sha256,
                    source_url,
                    media_type,
                    label,
                )
        return {"sha256": sha256, "proof_ref_id": ref["id"], "size_bytes": len(content), "deduplicated": True}

    async def check_integrity(self) -> IntegrityReport:
        """Détecte les incohérences base/fichiers (CON-02 §3, OSIA-I-10).

        - fichier présent sans ligne proof_files -> orphelin (supprimable, jamais une preuve référencée)
        - ligne proof_files sans fichier -> missing (signalé, jamais réécrit silencieusement)
        """
        rows = await self.repo.list_proof_files()
        referenced = {r["sha256"]: r["path"] for r in rows}
        missing: list[str] = []
        for sha256, relpath in referenced.items():
            if not (self.paths.data_dir / relpath).exists():
                missing.append(sha256)
        orphans: list[str] = []
        for path in self.paths.proofs_dir.rglob("*"):
            if path.is_file() and path.parent.name != "incoming" and path.suffix != ".part":
                sha256 = path.name
                if sha256 not in referenced:
                    orphans.append(str(path))
        for path in self.paths.incoming_dir.glob("*.part"):
            orphans.append(str(path))
        return IntegrityReport(orphan_files=orphans, missing_files=missing)

    async def purge_orphans(self, report: IntegrityReport) -> int:
        """Supprime uniquement les fichiers orphelins non référencés (OSIA-I-14)."""
        removed = 0
        for orphan in report.orphan_files:
            path = pathlib.Path(orphan)
            if path.exists():
                path.unlink()
                removed += 1
        return removed

    def read_proof(self, sha256: str) -> bytes | None:
        path = self._content_path(sha256)
        if path.exists():
            return path.read_bytes()
        return None
