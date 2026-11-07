from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import re
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

# Plafonds anti zip-bomb et anti écriture hors stockage (audit issue #17 F01) : vérifiés AVANT
# toute lecture/écriture, complétés par des lectures bornées (la taille déclarée d'une entrée ZIP
# peut mentir).
MAX_ZIP_ENTRIES = 10_000
MAX_ENTRY_BYTES = 100 * 1024 * 1024  # 100 Mo décompressés par entrée
MAX_TOTAL_BYTES = 512 * 1024 * 1024  # 512 Mo décompressés au total
MAX_MANIFEST_BYTES = 10 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TABLE_RE = re.compile(r"^[a-z_]+$")
_ENC_RE = re.compile(r"^enc/[0-9]{6}\.enc$")


class ArchiveError(Exception):
    """Archive illisible, version non supportee ou integrite non verifiee (T7.2/T7.7)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_valid_sha256(name: Any) -> bool:
    """Un digest de preuve n'est utilisable comme composante de chemin que s'il fait 64 hex."""
    return isinstance(name, str) and bool(_SHA256_RE.match(name))


def _safe_entry_name(name: Any) -> bool:
    """Nom d'entrée ZIP sûr : chaîne non vide, chemin relatif POSIX, sans '..' ni antislash."""
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    p = pathlib.PurePosixPath(name)
    if p.is_absolute():
        return False
    return all(part != ".." for part in p.parts)


def _validate_zip_layout(zf: zipfile.ZipFile) -> None:
    """Rejette l'archive avant toute lecture : noms non sûrs, liens symboliques, doublons,
    plafonds de volume (nombre d'entrées, taille déclarée par entrée et au total)."""
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ArchiveError(f"archive trop volumineuse: {len(infos)} entrées (max {MAX_ZIP_ENTRIES})")
    seen: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        if not _safe_entry_name(name):
            raise ArchiveError(f"nom d'entrée non sûr refusé: {name!r}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ArchiveError(f"lien symbolique refusé: {name!r}")
        if name in seen:
            raise ArchiveError(f"entrée dupliquée refusée: {name!r}")
        seen.add(name)
        if info.file_size > MAX_ENTRY_BYTES:
            raise ArchiveError(f"entrée trop volumineuse: {name!r} ({info.file_size} o, max {MAX_ENTRY_BYTES})")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ArchiveError(f"volume décompressé total dépassé (max {MAX_TOTAL_BYTES} o)")


def _bounded_read(zf: zipfile.ZipFile, name: str, max_bytes: int) -> bytes:
    """Lecture bornée d'une entrée ZIP : au plus max_bytes+1 octets lus (la taille déclarée peut
    mentir, ex. zip bomb), puis rejet si le plafond est dépassé."""
    with zf.open(name) as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ArchiveError(f"entrée dépassant le plafond décompressé ({max_bytes} o): {name!r}")
    return data


def _validate_manifest_path(path: Any) -> None:
    """Schéma strict des chemins du manifeste (F01) : `data/<table>.json(l)` ou
    `proofs/<sha256>` avec un digest 64 hex — jamais de chemin absolu ni de traversée."""
    if not _safe_entry_name(path):
        raise ArchiveError(f"chemin de manifeste non sûr: {path!r}")
    if path.startswith(PROOF_PREFIX):
        if not is_valid_sha256(path[len(PROOF_PREFIX):]):
            raise ArchiveError(f"nom de preuve invalide (64 hex attendus): {path!r}")
    elif path.startswith(DATA_PREFIX):
        rest = path[len(DATA_PREFIX):]
        if "/" in rest or not (rest.endswith(".jsonl") or rest.endswith(".json")):
            raise ArchiveError(f"chemin de données invalide: {path!r}")
    else:
        raise ArchiveError(f"préfixe de chemin inconnu: {path!r}")


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
    for table in payload:
        if not _TABLE_RE.match(table):
            raise ArchiveError(f"nom de table invalide: {table!r}")
    for sha256 in proofs:
        if not is_valid_sha256(sha256):
            raise ArchiveError(f"clé de preuve invalide (64 hex attendus): {sha256!r}")
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


def _load_json(raw: bytes, what: str) -> dict:
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArchiveError(f"contenu illisible ({what})") from exc
    if not isinstance(obj, dict):
        raise ArchiveError(f"contenu invalide ({what})")
    return obj


def read_and_verify(src, passphrase: Optional[str] = None) -> tuple[dict, dict, zipfile.ZipFile, ArchiveCrypto, dict[str, bytes]]:
    """Lit meta.json/manifest.json (clair ou dechiffre) avec verification d'integrite (T7.2).

    Retourne aussi `raw` : nom d'entrée ZIP -> contenu brut lu UNE SEULE FOIS pendant la
    vérification (réserve audit PR#18 : évite la double lecture de chaque entrée par
    `extract_payload` via `preloaded=raw`)."""
    crypto = ArchiveCrypto(passphrase)
    zf = _read_zip(src)
    _validate_zip_layout(zf)
    names = set(zf.namelist())
    if MANIFEST in names and META not in names:
        manifest = _load_json(_bounded_read(zf, MANIFEST, MAX_MANIFEST_BYTES), MANIFEST)
        if manifest.get("format") != FORMAT:
            raise ArchiveError("format inconnu (attendu: osia-archive)")
        if str(manifest.get("format_version")) != FORMAT_VERSION:
            raise ArchiveError(f"version non supportee: {manifest.get('format_version')} (attendu {FORMAT_VERSION})")
        if not isinstance(manifest.get("files"), list):
            raise ArchiveError("manifeste invalide : files absent")
        raw = _verify_files(zf, manifest["files"], encrypted=False)
        return {}, manifest, zf, crypto, raw
    if META in names:
        meta = _load_json(_bounded_read(zf, META, MAX_MANIFEST_BYTES), META)
        if meta.get("format") != FORMAT:
            raise ArchiveError("format inconnu (attendu: osia-archive)")
        if str(meta.get("format_version")) != FORMAT_VERSION:
            raise ArchiveError(f"version non supportee: {meta.get('format_version')} (attendu {FORMAT_VERSION})")
        try:
            key = crypto.key_from_params(passphrase, meta["kdf"])
            nonce = base64.b64decode(meta["manifest_nonce_b64"])
            manifest_enc = meta["manifest_enc"]
        except (KeyError, ValueError, TypeError) as exc:
            raise ArchiveError("meta.json invalide : parametres de chiffrement absents ou illisibles") from exc
        if not isinstance(manifest_enc, str) or (manifest_enc != "manifest.json.enc" and not _ENC_RE.match(manifest_enc)) or manifest_enc not in names:
            raise ArchiveError("meta.json invalide : manifeste chiffré absent ou nom non sûr")
        manifest = _load_json(crypto.decrypt(nonce, _bounded_read(zf, manifest_enc, MAX_ENTRY_BYTES), key), "manifeste chiffre")
        if not isinstance(manifest.get("files"), list):
            raise ArchiveError("manifeste invalide : files absent")
        raw = _verify_files(zf, manifest["files"], encrypted=True, key=key, crypto=crypto)
        return meta, manifest, zf, crypto, raw
    raise ArchiveError("archive .osia invalide : manifeste absent")


def read_meta_and_manifest(src, passphrase: Optional[str] = None) -> tuple[dict, dict, zipfile.ZipFile, ArchiveCrypto]:
    """Lit meta.json/manifest.json (clair ou dechiffre) avec verification d'integrite (T7.2).

    Compatibilité : délègue à `read_and_verify` et ignore la carte des contenus lus."""
    meta, manifest, zf, crypto, _raw = read_and_verify(src, passphrase)
    return meta, manifest, zf, crypto


def _verify_files(zf: zipfile.ZipFile, files: list[dict[str, Any]], *, encrypted: bool, key: bytes | None = None, crypto: ArchiveCrypto | None = None) -> dict[str, bytes]:
    """Vérification d'intégrité stricte (T7.2, F01) : schéma des chemins, digest 64 hex,
    lecture bornée de chaque entrée, et pour une preuve le nom de fichier DOIT être le digest
    de son contenu (un nom trompeur est rejeté même si le manifeste est cohérent).

    Retourne nom d'entrée -> contenu brut (déchiffré si chiffré) lu une seule fois, pour
    `extract_payload(preloaded=...)` (réserve audit PR#18 : plus de double lecture)."""
    errors: list[str] = []
    names = set(zf.namelist())
    total = 0
    raw_map: dict[str, bytes] = {}
    for entry in files:
        path = entry.get("path")
        try:
            _validate_manifest_path(path)
        except ArchiveError as exc:
            errors.append(str(exc))
            continue
        if not is_valid_sha256(entry.get("sha256")):
            errors.append(f"empreinte invalide (64 hex attendus): {path}")
            continue
        target = entry.get("enc") if encrypted else path
        if encrypted and (not isinstance(target, str) or not _ENC_RE.match(target)):
            errors.append(f"nom d'entrée chiffrée non sûr: {target!r}")
            continue
        if target not in names:
            errors.append(f"fichier absent: {path}")
            continue
        try:
            raw = _bounded_read(zf, target, MAX_ENTRY_BYTES)
        except ArchiveError as exc:
            errors.append(str(exc))
            continue
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ArchiveError(f"volume décompressé total dépassé (max {MAX_TOTAL_BYTES} o)")
        if encrypted:
            nonce_b64 = entry.get("nonce_b64")
            if not isinstance(nonce_b64, str):
                errors.append(f"nonce absent ou illisible: {path}")
                continue
            try:
                raw = crypto.decrypt(base64.b64decode(nonce_b64), raw, key)
            except (CryptoError, ValueError) as exc:
                errors.append(f"dechiffrement echoue: {path} ({exc})")
                continue
        digest = sha256_bytes(raw)
        if digest != entry["sha256"]:
            errors.append(f"empreinte SHA-256 invalide: {path}")
            continue
        if path.startswith(PROOF_PREFIX) and path[len(PROOF_PREFIX):] != digest:
            errors.append(f"nom de preuve ne correspond pas à son empreinte: {path}")
        raw_map[target] = raw
    if errors:
        raise ArchiveError("integrite non verifiee: " + "; ".join(errors))
    return raw_map


def extract_payload(zf: zipfile.ZipFile, manifest: dict, *, encrypted: bool, key: bytes | None = None, crypto: ArchiveCrypto | None = None, preloaded: dict[str, bytes] | None = None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes]]:
    """Retourne (payload par table, preuves sha256 -> contenu) apres verification d'integrite.

    F01 : chaque chemin est re-validé ici (défense en profondeur), les lectures sont bornées,
    le volume total est plafonné, et une preuve n'est indexée que par un nom 64 hex validé —
    jamais par un chemin fourni brut par l'archive.

    `preloaded` : contenus déjà lus/déchiffrés par `_verify_files` (clé = nom d'entrée ZIP) ;
    évite de relire chaque entrée (réserve audit PR#18). Toute entrée malformée (clé absente,
    nonce illisible, déchiffrement impossible) lève ArchiveError — jamais KeyError/CryptoError
    brut (réserve audit PR#18)."""
    payload: dict[str, list[dict[str, Any]]] = {}
    proofs: dict[str, bytes] = {}
    total = 0
    for entry in manifest["files"]:
        path = entry.get("path")
        _validate_manifest_path(path)  # lève ArchiveError si absent/non sûr (jamais KeyError)
        target = entry.get("enc") if encrypted else path
        if encrypted and (not isinstance(target, str) or not _ENC_RE.match(target)):
            raise ArchiveError(f"nom d'entrée chiffrée non sûr: {target!r}")
        if preloaded is not None:
            if target not in preloaded:
                raise ArchiveError(f"contenu non pré-vérifié: {path}")
            raw = preloaded[target]  # déjà déchiffré par _verify_files si chiffré
        else:
            try:
                raw = _bounded_read(zf, target, MAX_ENTRY_BYTES)
            except ArchiveError:
                raise
            except KeyError as exc:
                raise ArchiveError(f"fichier absent: {path}") from exc
            if encrypted:
                nonce_b64 = entry.get("nonce_b64")
                if not isinstance(nonce_b64, str):
                    raise ArchiveError(f"nonce absent ou illisible: {path}")
                try:
                    raw = crypto.decrypt(base64.b64decode(nonce_b64), raw, key)
                except (CryptoError, ValueError) as exc:
                    raise ArchiveError(f"dechiffrement echoue: {path} ({exc})") from exc
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ArchiveError(f"volume décompressé total dépassé (max {MAX_TOTAL_BYTES} o)")
        if path.startswith(PROOF_PREFIX):
            name = path[len(PROOF_PREFIX):]
            if not is_valid_sha256(name):
                raise ArchiveError(f"nom de preuve invalide (64 hex attendus): {path!r}")
            proofs[name] = raw
            continue
        table = path[len(DATA_PREFIX):].removesuffix(".jsonl").removesuffix(".json")
        if table == "investigation":
            table = "investigations"
        try:
            text = raw.decode("utf-8").strip()
            rows = [json.loads(line) for line in text.splitlines() if line.strip()] if text else []
            if path.endswith(".json"):
                rows = [json.loads(text)] if text else []
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"contenu illisible: {path} ({exc})") from exc
        payload[table] = rows
    return payload, proofs
