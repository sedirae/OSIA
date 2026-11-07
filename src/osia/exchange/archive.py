from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import zipfile
from typing import Any, Optional

from .crypto import CIPHER, ArchiveCrypto, CryptoError

FORMAT = "osia-archive"
FORMAT_VERSION = "1.0"

DATA_PREFIX = "data/"
PROOF_PREFIX = "proofs/"
ENC_PREFIX = "enc/"
MANIFEST = "manifest.json"
META = "meta.json"


class ArchiveError(Exception):
    """Archive illisible, version non supportee ou integrite non verifiee (T7.2/T7.7)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def build_manifest(
    *,
    osia_version: str,
    scope: dict[str, Any],
    counts: dict[str, int],
    warnings: list[str],
    files: list[dict[str, Any]],
    encrypted: bool,
) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "created_at": scope.get("created_at"),
        "osia_version": osia_version,
        "encrypted": encrypted,
        "scope": scope,
        "counts": counts,
        "warnings": warnings,
        "files": files,
    }


def write_archive(
    dest: pathlib.Path,
    *,
    payload: dict[str, list[dict[str, Any]]],
    proofs: dict[str, bytes],
    scope: dict[str, Any],
    warnings: list[str],
    osia_version: str,
    encrypt: bool = False,
    passphrase: Optional[str] = None,
) -> dict[str, Any]:
    """Ecrit l'archive .osia sur disque (ZIP, ZIP64 automatique) et retourne le manifeste.

    Clair : manifest.json + data/*.jsonl + proofs/<sha256>. Chiffre : meta.json clair
    (sans aucun nom interne) + manifest.json.enc + enc/<n>.enc (CON-15, T7.3)."""
    crypto = ArchiveCrypto(passphrase)
    counts = {t: len(rows) for t, rows in payload.items()}
    entries: list[tuple[str, bytes]] = []
    for table, rows in payload.items():
        name = "investigation.json" if table == "investigations" else f"{table}.jsonl"
        body = "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)
        if rows and table == "investigations":
            body = json.dumps(rows[0], ensure_ascii=False, default=str)
        entries.append((DATA_PREFIX + name, body.encode("utf-8") + (b"" if body.endswith("\n") or not body else b"\n")))
    for sha256, content in proofs.items():
        entries.append((PROOF_PREFIX + sha256, content))

    files: list[dict[str, Any]] = []
    if not encrypt:
        for path, content in entries:
            files.append({"path": path, "sha256": sha256_bytes(content), "size_bytes": len(content)})
        manifest = build_manifest(osia_version=osia_version, scope=scope, counts=counts, warnings=warnings, files=files, encrypted=False)
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            zf.writestr(MANIFEST, _json_bytes(manifest))
            for path, content in entries:
                zf.writestr(path, content)
        return manifest

    if not passphrase:
        raise CryptoError("phrase secrete requise pour une archive chiffree")
    salt = crypto.new_salt()
    key = crypto.derive_key(passphrase, salt)
    enc_files: list[dict[str, Any]] = []
    enc_entries: list[tuple[str, bytes]] = []
    for i, (path, content) in enumerate(entries):
        nonce, ct = crypto.encrypt(content, key)
        enc_name = f"{ENC_PREFIX}{i:06d}.enc"
        enc_entries.append((enc_name, ct))
        enc_files.append({
            "path": path,
            "enc": enc_name,
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
        })
    manifest = build_manifest(osia_version=osia_version, scope=scope, counts=counts, warnings=warnings, files=enc_files, encrypted=True)
    nonce, ct = crypto.encrypt(_json_bytes(manifest), key)
    meta = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "encrypted": True,
        "cipher": CIPHER,
        "kdf": crypto.kdf_params(salt),
        "manifest_enc": "manifest.json.enc",
        "manifest_nonce_b64": base64.b64encode(nonce).decode("ascii"),
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.writestr(META, _json_bytes(meta))
        zf.writestr("manifest.json.enc", ct)
        for name, content in enc_entries:
            zf.writestr(name, content)
    return manifest


def _read_zip(src: pathlib.Path | bytes | io.BufferedIOBase) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(src, "r")
    except zipfile.BadZipFile as exc:
        raise ArchiveError("fichier non reconnu comme archive ZIP (.osia attendu)") from exc


def read_meta_and_manifest(src, passphrase: Optional[str] = None) -> tuple[dict, dict, zipfile.ZipFile, ArchiveCrypto]:
    """Lit meta.json/manifest.json (clair ou dechiffre) avec verification d'integrite (T7.2)."""
    crypto = ArchiveCrypto(passphrase)
    zf = _read_zip(src)
    names = set(zf.namelist())
    if MANIFEST in names and META not in names:
        raw = zf.read(MANIFEST)
        manifest = json.loads(raw)
        if manifest.get("format") != FORMAT:
            raise ArchiveError("format inconnu (attendu: osia-archive)")
        if str(manifest.get("format_version")) != FORMAT_VERSION:
            raise ArchiveError(f"version non supportee: {manifest.get('format_version')} (attendu {FORMAT_VERSION})")
        _verify_files(zf, manifest["files"], encrypted=False)
        return {}, manifest, zf, crypto
    if META in names:
        meta = json.loads(zf.read(META))
        if meta.get("format") != FORMAT:
            raise ArchiveError("format inconnu (attendu: osia-archive)")
        if str(meta.get("format_version")) != FORMAT_VERSION:
            raise ArchiveError(f"version non supportee: {meta.get('format_version')} (attendu {FORMAT_VERSION})")
        key = crypto.key_from_params(passphrase, meta["kdf"])
        nonce = base64.b64decode(meta["manifest_nonce_b64"])
        manifest = json.loads(crypto.decrypt(nonce, zf.read(meta["manifest_enc"]), key))
        _verify_files(zf, manifest["files"], encrypted=True, key=key, crypto=crypto)
        return meta, manifest, zf, crypto
    raise ArchiveError("archive .osia invalide : manifeste absent")


def _verify_files(zf: zipfile.ZipFile, files: list[dict[str, Any]], *, encrypted: bool, key: bytes | None = None, crypto: ArchiveCrypto | None = None) -> None:
    errors: list[str] = []
    names = set(zf.namelist())
    for entry in files:
        target = entry["enc"] if encrypted else entry["path"]
        if target not in names:
            errors.append(f"fichier absent: {entry['path']}")
            continue
        raw = zf.read(target)
        if encrypted:
            try:
                raw = crypto.decrypt(base64.b64decode(entry["nonce_b64"]), raw, key)
            except CryptoError as exc:
                errors.append(f"dechiffrement echoue: {entry['path']} ({exc})")
                continue
        digest = sha256_bytes(raw)
        if digest != entry["sha256"]:
            errors.append(f"empreinte SHA-256 invalide: {entry['path']}")
    if errors:
        raise ArchiveError("integrite non verifiee: " + "; ".join(errors))


def extract_payload(zf: zipfile.ZipFile, manifest: dict, *, encrypted: bool, key: bytes | None = None, crypto: ArchiveCrypto | None = None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes]]:
    """Retourne (payload par table, preuves sha256 -> contenu) apres verification d'integrite."""
    payload: dict[str, list[dict[str, Any]]] = {}
    proofs: dict[str, bytes] = {}
    for entry in manifest["files"]:
        path = entry["path"]
        raw = zf.read(entry["enc"] if encrypted else path)
        if encrypted:
            raw = crypto.decrypt(base64.b64decode(entry["nonce_b64"]), raw, key)
        if path.startswith(PROOF_PREFIX):
            proofs[path[len(PROOF_PREFIX):]] = raw
            continue
        table = path[len(DATA_PREFIX):].removesuffix(".jsonl").removesuffix(".json")
        if table == "investigation":
            table = "investigations"
        text = raw.decode("utf-8").strip()
        rows = [json.loads(line) for line in text.splitlines() if line.strip()] if text else []
        if path.endswith(".json"):
            rows = [json.loads(text)]
        payload[table] = rows
    return payload, proofs
