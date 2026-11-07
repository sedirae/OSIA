"""Régression audit issue #17 — F01 (import confiné et borné) et F02 (transport lié au contrôle
SSRF, lectures bornées, parsing isolé).

Ces tests INVERSENT les sondes de l'annexe de l'audit (qui affirmaient le comportement
défectueux) : ils exigent ici le comportement corrigé. Aucun réseau réel, aucune base requise
pour la plupart (doubles aux frontières), sauf mention contraire."""

import hashlib
import io
import json
import pathlib
import socket
import zipfile

import pytest

from osia.config import Paths
from osia.exchange import archive as archive_mod
from osia.exchange.archive import (
    MANIFEST,
    ArchiveError,
    _bounded_read,
    is_valid_sha256,
    read_meta_and_manifest,
    write_archive,
)
from osia.exchange.service import ExchangeService
from osia.netguard import NetworkDeny, NetworkGuard, NetworkPolicy, PinnedTarget, RequestContext
from osia.nethttp import PinnedResolver, drop_credential_headers, read_bounded
from osia.connectors.http import aiohttp_fetch
from osia.ai.real import _aiohttp_get, _aiohttp_post
from osia.connectors.real import extract_text_from_pdf, extract_text_from_pdf_isolated


# ---------- helpers ----------


def make_paths(tmp_path) -> Paths:
    paths = Paths(**{k: tmp_path / k for k in ("config_dir", "data_dir", "cache_dir", "log_dir", "backup_dir")})
    paths.ensure()
    return paths


def make_service(tmp_path) -> ExchangeService:
    return ExchangeService(None, None, None, None, make_paths(tmp_path))


def craft_archive(dest: pathlib.Path, entries: dict[str, bytes], *, manifest_files=None) -> pathlib.Path:
    """Archive .osia fabriquée à la main (simule un attaquant) : entrées brutes + manifeste."""
    files = manifest_files
    if files is None:
        files = [
            {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
            for name, content in entries.items()
        ]
    manifest = {
        "format": "osia-archive",
        "format_version": "1.0",
        "encrypted": False,
        "scope": {},
        "counts": {},
        "warnings": [],
        "files": files,
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(MANIFEST, json.dumps(manifest))
        for name, content in entries.items():
            zf.writestr(name, content)
    return dest


def make_pdf(text: str) -> bytes:
    """PDF minimal textuel fabriqué à la main (même fixture que test_con0708)."""
    content = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode())
    return out.getvalue()


# ---------- F01 : chemins, empreintes, volumes ----------


async def test_f01_archive_chemin_absolu_refuse_avant_toute_ecriture(tmp_path):
    """Sonde audit inversée : un nom de preuve absolu ne doit JAMAIS produire d'écriture hors
    du répertoire de données (l'archive est rejetée avant staging)."""
    service = make_service(tmp_path)
    marker = tmp_path / "outside_data_marker"
    dest = craft_archive(tmp_path / "crafted.osia", {str(marker): b"audit-marker"})
    with pytest.raises(ArchiveError):
        read_meta_and_manifest(dest)
    with pytest.raises(ArchiveError):
        await service.apply_import(dest)
    assert not marker.exists()
    assert not (service.paths.data_dir / "proofs" / "sha256").exists() or not any(
        (service.paths.data_dir / "proofs").rglob("*")
    )


async def test_f01_archive_traversee_et_nom_non_sha_refuses(tmp_path):
    service = make_service(tmp_path)
    for bad_name in ("proofs/../../escape", "proofs/deadbeef", "proofs/" + "a" * 63, "data/../manifest.json"):
        dest = craft_archive(tmp_path / "bad.osia", {bad_name: b"x"})
        with pytest.raises(ArchiveError):
            read_meta_and_manifest(dest)
        with pytest.raises(ArchiveError):
            await service.apply_import(dest)


async def test_f01_archive_empreinte_trompeuse_refusee(tmp_path):
    """Le nom d'une preuve doit être ÉGAL au SHA-256 de son contenu, même si le manifeste est
    cohérent avec un autre digest."""
    content = b"contenu reel"
    fake_name = "proofs/" + "a" * 64  # 64 hex, mais pas le digest de content
    dest = craft_archive(
        tmp_path / "lie.osia",
        {fake_name: content},
        manifest_files=[{"path": fake_name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}],
    )
    with pytest.raises(ArchiveError) as exc:
        read_meta_and_manifest(dest)
    assert "empreinte" in str(exc.value)


async def test_f01_archive_lien_symbolique_refuse(tmp_path):
    dest = tmp_path / "symlink.osia"
    with zipfile.ZipFile(dest, "w") as zf:
        zi = zipfile.ZipInfo("proofs/" + "b" * 64)
        zi.external_attr = (0o120777 << 16)
        zf.writestr(zi, b"")
        zf.writestr(MANIFEST, json.dumps({"format": "osia-archive", "format_version": "1.0", "encrypted": False, "files": []}))
    with pytest.raises(ArchiveError):
        read_meta_and_manifest(dest)


async def test_f01_archive_plafonds_volume(tmp_path, monkeypatch):
    """Plafonds anti zip-bomb : nombre d'entrées, taille par entrée, volume total."""
    big = b"x" * 4096
    dest = craft_archive(tmp_path / "big.osia", {"data/x.jsonl": big})
    monkeypatch.setattr(archive_mod, "MAX_ENTRY_BYTES", 1024)
    with pytest.raises(ArchiveError):
        read_meta_and_manifest(dest)
    monkeypatch.setattr(archive_mod, "MAX_ENTRY_BYTES", 100 * 1024 * 1024)
    monkeypatch.setattr(archive_mod, "MAX_TOTAL_BYTES", 2048)
    dest2 = craft_archive(tmp_path / "total.osia", {"data/a.jsonl": b"x" * 1500, "data/b.jsonl": b"y" * 1500})
    with pytest.raises(ArchiveError):
        read_meta_and_manifest(dest2)
    monkeypatch.setattr(archive_mod, "MAX_TOTAL_BYTES", 512 * 1024 * 1024)
    monkeypatch.setattr(archive_mod, "MAX_ZIP_ENTRIES", 2)
    dest3 = craft_archive(tmp_path / "many.osia", {"data/a.jsonl": b"", "data/b.jsonl": b"", "data/c.jsonl": b""})
    with pytest.raises(ArchiveError):
        read_meta_and_manifest(dest3)


def test_f01_bounded_read_backstop_sur_taille_declaree_trompeuse(tmp_path):
    """La lecture bornée est le backstop quand la taille déclarée de l'entrée ZIP ment."""
    dest = tmp_path / "entry.osia"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("data/x.jsonl", b"0123456789")
    with zipfile.ZipFile(dest) as zf:
        assert _bounded_read(zf, "data/x.jsonl", 10) == b"0123456789"
        with pytest.raises(ArchiveError):
            _bounded_read(zf, "data/x.jsonl", 4)


async def test_f01_proofs_bytes_ne_lit_jamais_hors_stockage(tmp_path):
    """Sonde audit inversée : un champ `path` importé pointant vers un fichier hôte externe ne
    doit plus être suivi ; seule la voie canonique reconstruite depuis le SHA-256 est lue."""
    service = make_service(tmp_path)
    marker = tmp_path / "outside_read_marker"
    marker.write_bytes(b"private-audit-marker")
    sha = "0" * 64
    out = await service._proofs_bytes([{"sha256": sha, "path": str(marker)}])
    assert out == {}  # rien lu hors du stockage
    # cas positif : la voie canonique fonctionne
    canonical = service.paths.proofs_dir / "sha256" / sha[:2] / sha[2:4] / sha
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"contenu canonique")
    out = await service._proofs_bytes([{"sha256": sha, "path": str(marker)}])
    assert out == {sha: b"contenu canonique"}


async def test_f01_stage_proof_files_valide_et_confine(tmp_path):
    service = make_service(tmp_path)
    # digest invalide (chemin absolu) : refus, aucune écriture
    with pytest.raises(ArchiveError):
        service._stage_proof_files({str(tmp_path / "evil"): b"x"})
    assert not (tmp_path / "evil").exists()
    # digest valide mais ne correspond pas au contenu : refus
    with pytest.raises(ArchiveError):
        service._stage_proof_files({"a" * 64: b"contenu"})
    # digest correct : staging canonique sous proofs_dir
    content = b"preuve importee"
    sha = hashlib.sha256(content).hexdigest()
    staged = service._stage_proof_files({sha: content})
    assert staged[sha]["path"] == f"proofs/sha256/{sha[:2]}/{sha[2:4]}/{sha}"
    final = service.paths.proofs_dir / "sha256" / sha[:2] / sha[2:4] / sha
    assert final.read_bytes() == content
    assert final.resolve().is_relative_to(service.paths.proofs_dir.resolve())


async def test_f01_write_archive_refuse_cle_preuve_invalide(tmp_path):
    with pytest.raises(ArchiveError):
        write_archive(
            tmp_path / "a.osia",
            payload={},
            proofs={str(tmp_path / "x"): b"y"},
            scope={},
            warnings=[],
            osia_version="test",
        )


def test_f01_is_valid_sha256():
    assert is_valid_sha256("a" * 64)
    assert not is_valid_sha256("a" * 63)
    assert not is_valid_sha256("A" * 64)
    assert not is_valid_sha256("/abs/path")
    assert not is_valid_sha256(None)
    assert not is_valid_sha256(123)


# ---------- F02 : transport lié au contrôle SSRF ----------


async def test_f02_guarded_request_epingle_les_ips_validees_au_transport():
    """Sonde audit inversée : le fetch reçoit un ctx dont les IPs épinglées sont exactement
    celles validées par resolve_and_check (le résultat n'est plus abandonné)."""

    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    seen = []

    async def fetch(url, ctx=None):
        seen.append((url, ctx))
        return 200, {}, b"ok"

    fetch.accepts_ctx = True
    guard = NetworkGuard(NetworkPolicy(allowed_domains={"example.test"}, min_interval_seconds=0), resolver=resolve)
    status, _, body = await guard.guarded_request(fetch, "https://example.test/resource")
    assert status == 200 and body == b"ok"
    assert len(seen) == 1
    url, ctx = seen[0]
    assert url == "https://example.test/resource"
    assert isinstance(ctx, RequestContext)
    assert ctx.pinned == PinnedTarget(host="example.test", port=443, ips=["93.184.216.34"])
    assert ctx.same_origin is True
    assert ctx.max_bytes == guard.policy.max_bytes


async def test_f02_guarded_request_fetch_legacy_sans_ctx_toujours_supporte():
    """Compatibilité : un fetch simple `fetch(url)` (tests existants) continue de fonctionner."""

    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    async def fetch(url):
        assert url == "https://a.test/1"
        return 200, {}, b"ok"

    guard = NetworkGuard(NetworkPolicy(allowed_domains={"a.test"}, min_interval_seconds=0), resolver=resolve)
    status, _, body = await guard.guarded_request(fetch, "https://a.test/1")
    assert (status, body) == (200, b"ok")


async def test_f02_redirect_inter_origines_same_origin_false():
    """Sur redirection vers une autre origine, le ctx transmis passe same_origin=False pour
    que le fetch y supprime les credentials."""

    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    seen = []

    async def fetch(url, ctx=None):
        seen.append(ctx.same_origin)
        if url == "https://a.test/1":
            return 302, {"location": "https://b.test/2"}, b""
        if url == "https://a.test/same":
            return 302, {"location": "https://a.test/other"}, b""
        return 200, {}, b"ok"

    fetch.accepts_ctx = True
    guard = NetworkGuard(
        NetworkPolicy(allowed_domains={"a.test", "b.test"}, min_interval_seconds=0, max_redirects=3),
        resolver=resolve,
    )
    await guard.guarded_request(fetch, "https://a.test/1")
    assert seen == [True, False]
    seen.clear()
    await guard.guarded_request(fetch, "https://a.test/same")
    assert seen == [True, True]


async def test_f02_pinned_resolver_ne_retourne_que_les_ips_validees():
    resolver = PinnedResolver(PinnedTarget(host="example.test", port=443, ips=["93.184.216.34", "2001:db8::1"]))
    out = await resolver.resolve("example.test", 443)
    assert {e["host"] for e in out} == {"93.184.216.34", "2001:db8::1"}
    assert all(e["hostname"] == "example.test" for e in out)  # SNI/Host conservés
    assert all(e["port"] == 443 for e in out)
    with pytest.raises(NetworkDeny):
        await resolver.resolve("evil.test", 443)


class _FakeContent:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeResp:
    def __init__(self, chunks, headers=None):
        self.content = _FakeContent(chunks)
        self.headers = headers or {}


async def test_f02_read_bounded_content_length_puis_streaming():
    # Content-Length au-delà du plafond : refus immédiat
    with pytest.raises(NetworkDeny) as exc:
        await read_bounded(_FakeResp([], {"Content-Length": "999999"}), max_bytes=1024, host="h.test")
    assert exc.value.reason == "taille_depassee"
    # corps chunké dépassant le plafond en streaming : refus sans tout allouer
    with pytest.raises(NetworkDeny):
        await read_bounded(_FakeResp([b"x" * 64 * 1024] * 100), max_bytes=1024, host="h.test")
    # cas nominal
    body = await read_bounded(_FakeResp([b"abc", b"def"]), max_bytes=1024, host="h.test")
    assert body == b"abcdef"


def test_f02_drop_credential_headers():
    headers = {"Authorization": "Bearer secret", "Cookie": "s=1", "Content-Type": "application/json"}
    same = RequestContext(pinned=None, max_bytes=10, same_origin=True)
    cross = RequestContext(pinned=None, max_bytes=10, same_origin=False)
    assert drop_credential_headers(headers, same) == headers
    assert drop_credential_headers(headers, None) == headers
    out = drop_credential_headers(headers, cross)
    assert "Authorization" not in out and "Cookie" not in out
    assert out["Content-Type"] == "application/json"


def test_f02_fetchs_reels_acceptent_le_ctx():
    assert getattr(aiohttp_fetch, "accepts_ctx", False) is True
    post = _aiohttp_post({}, {"Authorization": "Bearer k"}, 5)
    get = _aiohttp_get({"Authorization": "Bearer k"}, 5)
    assert getattr(post, "accepts_ctx", False) is True
    assert getattr(get, "accepts_ctx", False) is True


# ---------- F02 : parsing documentaire isolé ----------


def test_f02_extraction_pdf_hors_processus_moteur():
    pdf = make_pdf("Hello OSIA")
    assert extract_text_from_pdf(pdf) == "Hello OSIA"


async def test_f02_extraction_pdf_isolee_async_et_rejet_document_corrompu():
    pdf = make_pdf("Hello OSIA")
    assert await extract_text_from_pdf_isolated(pdf) == "Hello OSIA"
    with pytest.raises(ValueError):
        await extract_text_from_pdf_isolated(b"ceci n'est pas un PDF")
