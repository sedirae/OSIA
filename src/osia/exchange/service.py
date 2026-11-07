from __future__ import annotations

import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..config import Paths
from ..events import EventBus
from ..ids import new_id
from ..store.files import FileStore
from ..store.repo import Repo
from .archive import (
    FORMAT_VERSION,
    ArchiveError,
    extract_payload,
    read_meta_and_manifest,
    sha256_bytes,
    write_archive,
)
from .crypto import CryptoError
from .dump import EXCLUDABLE, ImportConflictError, dump_investigation, import_payload, detect_conflicts

OSIA_VERSION = "0.1.0"


class ExchangeService:
    """Export/import des archives .osia et journal des exports (CON-14, T7.1-T7.8, D5).

    Export selectif avec empreintes SHA-256 et avertissements de chaine de preuve rompue
    (T7.4) ; chiffrement facultatif AES-256-GCM + Argon2id (CON-15) ; import supervise :
    verification d'integrite, preview des conflits, application transactionnelle sans
    aucun ecrasement silencieux et sans reprise de recherche (T7.6, D5.7.2)."""

    def __init__(self, pool: asyncpg.Pool, repo: Repo, bus: EventBus, filestore: FileStore, paths: Paths, report: Any = None):
        self.pool = pool
        self.repo = repo
        self.bus = bus
        self.filestore = filestore
        self.paths = paths
        self.report = report

    def _exports_dir(self, export_id: str) -> pathlib.Path:
        d = self.paths.data_dir / "exports" / export_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def _proofs_bytes(self, proof_rows: list[dict[str, Any]]) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for row in proof_rows:
            sha = row["sha256"]
            path = self.paths.data_dir / row["path"]
            if path.exists():
                out[sha] = path.read_bytes()
        return out

    async def export_investigation(
        self,
        investigation_id: str,
        *,
        format: str = "osia",
        branch_ids: Optional[list[str]] = None,
        include_proofs: bool = True,
        exclusions: Optional[set[str]] = None,
        encrypt: bool = False,
        passphrase: Optional[str] = None,
    ) -> dict[str, Any]:
        if format not in ("osia", "html", "both"):
            raise ArchiveError(f"format inconnu: {format}")
        exclusions = set(exclusions or set()) & EXCLUDABLE
        inv = await self.repo.get_investigation(investigation_id)
        if inv is None:
            raise ArchiveError(f"investigation inconnue: {investigation_id}")
        payload = await dump_investigation(self.pool, investigation_id, branch_ids=branch_ids, exclusions=exclusions)
        warnings: list[str] = []
        if exclusions:
            warnings.append("export partiel, tables exclues: " + ", ".join(sorted(exclusions)))
        if branch_ids:
            warnings.append("export restreint aux branches: " + ", ".join(branch_ids))
        proof_ids_used = {p for rows in (payload.get("assertions", []), payload.get("relations", [])) for r in rows for p in (r.get("proof_ids") or [])}
        proof_ids_have = {r["id"] for r in payload.get("proof_refs", [])}
        for pid in sorted(proof_ids_used - proof_ids_have):
            warnings.append(f"chaîne de preuve rompue : preuve {pid} référencée mais non exportée (T7.4)")
        if not include_proofs and payload.get("proof_refs"):
            warnings.append("binaires de preuves exclus ; seules les métadonnées figurent dans l'archive (T7.4)")

        export_id = new_id("exp")
        out_dir = self._exports_dir(export_id)
        proofs: dict[str, bytes] = {}
        if format in ("osia", "both") and include_proofs:
            proofs = await self._proofs_bytes(payload.get("proof_files", []))
        scope = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "investigation_ids": [investigation_id],
            "branch_ids": branch_ids,
            "include_proofs": include_proofs and format in ("osia", "both"),
            "exclusions": sorted(exclusions),
            "partial": bool(exclusions or branch_ids or not include_proofs),
        }
        files_out: list[dict[str, Any]] = []
        manifest = None
        if format in ("osia", "both"):
            dest = out_dir / "archive.osia"
            manifest = write_archive(
                dest,
                payload=payload,
                proofs=proofs,
                scope=scope,
                warnings=warnings,
                osia_version=OSIA_VERSION,
                encrypt=encrypt,
                passphrase=passphrase,
            )
            files_out.append({"file": "archive.osia", "sha256": sha256_bytes(dest.read_bytes()), "size_bytes": dest.stat().st_size})
        if format in ("html", "both"):
            html = await self.report.build(
                investigation_id,
                branch_ids=branch_ids,
                exclusions=exclusions | ({"proofs"} if not include_proofs else set()),
            ) if self.report is not None else None
            if html is not None:
                dest = out_dir / "rapport.html"
                dest.write_text(html, encoding="utf-8")
                files_out.append({"file": "rapport.html", "sha256": sha256_bytes(dest.read_bytes()), "size_bytes": dest.stat().st_size})
        counts = {t: len(rows) for t, rows in payload.items()}
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO exports (id, format, investigation_ids, branch_ids, exclusions, include_proofs, encrypted, partial, manifest_sha256, counts, warnings, files) "
                "VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb)",
                export_id,
                format,
                json.dumps([investigation_id]),
                json.dumps(branch_ids),
                json.dumps(sorted(exclusions)),
                include_proofs,
                encrypt,
                scope["partial"],
                sha256_bytes(json.dumps(manifest, sort_keys=True, default=str).encode()) if manifest else None,
                json.dumps(counts),
                json.dumps(warnings),
                json.dumps(files_out),
            )
        await self.bus.emit(
            type="export.created",
            investigation_id=investigation_id,
            payload={"export_id": export_id, "format": format, "encrypted": encrypt, "partial": scope["partial"], "counts": counts},
        )
        return {"export_id": export_id, "format": format, "encrypted": encrypt, "partial": scope["partial"], "counts": counts, "warnings": warnings, "files": files_out, "dir": str(out_dir), "manifest": manifest}

    async def preview_import(self, src: pathlib.Path, passphrase: Optional[str] = None) -> dict[str, Any]:
        meta, manifest, zf, crypto = read_meta_and_manifest(src, passphrase)
        try:
            payload, _ = extract_payload(zf, manifest, encrypted=manifest.get("encrypted", False), key=None if not manifest.get("encrypted") else crypto.key_from_params(passphrase, meta["kdf"]), crypto=crypto)
        finally:
            zf.close()
        async with self.pool.acquire() as conn:
            conflicts = await detect_conflicts(conn, payload)
        return {
            "format": manifest.get("format"),
            "format_version": manifest.get("format_version"),
            "encrypted": manifest.get("encrypted", False),
            "scope": manifest.get("scope"),
            "counts": manifest.get("counts"),
            "warnings": manifest.get("warnings", []),
            "conflicts": conflicts,
        }

    async def apply_import(
        self,
        src: pathlib.Path,
        *,
        mode: str = "add",
        on_conflict: str = "fail",
        passphrase: Optional[str] = None,
    ) -> dict[str, Any]:
        if mode not in ("add", "merge"):
            raise ArchiveError(f"mode inconnu: {mode}")
        if on_conflict not in ("fail", "skip"):
            raise ArchiveError(f"on_conflict inconnu: {on_conflict}")
        meta, manifest, zf, crypto = read_meta_and_manifest(src, passphrase)
        try:
            key = crypto.key_from_params(passphrase, meta["kdf"]) if manifest.get("encrypted") else None
            payload, proofs = extract_payload(zf, manifest, encrypted=manifest.get("encrypted", False), key=key, crypto=crypto)
        finally:
            zf.close()
        staged = self._stage_proof_files(proofs)
        for row in payload.get("proof_files", []):
            sha = row["sha256"]
            if sha in staged:
                row["path"] = staged[sha]["path"]
        report = await import_payload(self.pool, payload, mode=mode, on_conflict=on_conflict)
        inv_ids = [r["id"] for r in payload.get("investigations", [])]
        report["manifest_counts"] = manifest.get("counts")
        report["warnings"] = manifest.get("warnings", [])
        report["format_version"] = manifest.get("format_version", FORMAT_VERSION)
        for inv_id in inv_ids:
            await self.bus.emit(
                type="import.applied",
                investigation_id=inv_id if mode == "merge" else None,
                payload={"source": str(src), "mode": mode, "on_conflict": on_conflict, "counts": manifest.get("counts")},
            )
        return report

    def _stage_proof_files(self, proofs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
        """Phases 1-2 du protocole CON-02 (fichier avant base) pour les preuves importees."""
        staged: dict[str, dict[str, Any]] = {}
        self.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
        for sha, content in proofs.items():
            incoming = self.paths.incoming_dir / f"{sha}.part"
            final = self.paths.proofs_dir / "sha256" / sha[:2] / sha[2:4] / sha
            final.parent.mkdir(parents=True, exist_ok=True)
            with open(incoming, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if not final.exists():
                os.rename(incoming, final)
            else:
                incoming.unlink(missing_ok=True)
            staged[sha] = {"path": str(final.relative_to(self.paths.data_dir)), "size_bytes": len(content)}
        return staged

    async def list_exports(self) -> list[dict[str, Any]]:
        rows = await self.repo._fetch("SELECT * FROM exports ORDER BY created_at DESC")
        return rows

    async def get_export(self, export_id: str) -> Optional[dict[str, Any]]:
        return await self.repo._fetchrow("SELECT * FROM exports WHERE id = $1", export_id)


__all__ = ["ExchangeService", "ArchiveError", "CryptoError", "ImportConflictError"]
