import asyncio
import json
import stat

import pytest
from httpx import ASGITransport, AsyncClient

from osia.api import create_app
from osia.connectors.base import Connector, ConnectorManifest, TrustLevel
from osia.netguard import NetworkDeny, NetworkGuard, NetworkPolicy
from osia.security import SecretStore, run_isolated, IsolationLimits


async def client_for(engine):
    app = create_app(engine)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1")


def guard(**kw) -> NetworkGuard:
    policy = NetworkPolicy(**kw)
    return NetworkGuard(policy)


# ---------- NetworkGuard (T5.4) ----------

def test_check_url_scheme_et_domaine():
    g = guard(allowed_domains={"example.test"}, denied_domains={"evil.test"})
    assert g.check_url("https://example.test/x") == "example.test"
    assert g.check_url("https://sub.example.test/x") == "sub.example.test"
    with pytest.raises(NetworkDeny):
        g.check_url("ftp://example.test/x")
    with pytest.raises(NetworkDeny):
        g.check_url("https://evil.test/")
    with pytest.raises(NetworkDeny):
        g.check_url("https://other.test/")  # hors allowlist
    with pytest.raises(NetworkDeny):
        g.check_url("https://127.0.0.1/")  # IP littérale interne
    with pytest.raises(NetworkDeny):
        g.check_url("http://169.254.169.254/latest/meta-data")  # metadata cloud
    with pytest.raises(NetworkDeny):
        g.check_url("http://[::1]/")
    with pytest.raises(NetworkDeny):
        g.check_url("http://10.0.0.5/")


def test_check_url_ip_literale_publique_ne_contourne_pas_allowlist():
    """Correctif d'audit : une IP littérale publique hors allowlist est refusée
    (sinon l'allowlist de domaines serait contournée par simple IP littérale)."""
    g = guard(allowed_domains={"example.test"})
    with pytest.raises(NetworkDeny) as exc:
        g.check_url("https://93.184.216.34/x")
    assert exc.value.reason == "domaine_non_autorise"
    # allowlist vide = tout domaine/IP publique non bloqué autorisé
    g2 = guard()
    assert g2.check_url("https://93.184.216.34/x") == "93.184.216.34"


def test_check_url_port_invalide():
    g = guard()
    with pytest.raises(NetworkDeny) as exc:
        g.check_url("https://example.test:99999/x")
    assert exc.value.reason == "port_invalide"


async def test_resolve_and_check_anti_ssrf():
    async def fake_resolver_private(host, port):
        return [(2, 1, 6, "", ("192.168.1.10", port))]

    async def fake_resolver_ok(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    g = NetworkGuard(NetworkPolicy(), resolver=fake_resolver_private)
    with pytest.raises(NetworkDeny) as exc:
        await g.resolve_and_check("interne.test")
    assert exc.value.reason == "ssrf_ip_bloquee"
    g2 = NetworkGuard(NetworkPolicy(), resolver=fake_resolver_ok)
    assert await g2.resolve_and_check("exemple.test") == ["93.184.216.34"]


async def _fake_resolver_public(host, port):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


async def test_guarded_request_redirection_ssrf_bloquee():
    async def fetch(url):
        if url == "https://ok.test/start":
            return 302, {"location": "http://169.254.169.254/meta"}, b""
        return 200, {}, b"ok"

    g = NetworkGuard(NetworkPolicy(allowed_domains={"ok.test"}), resolver=_fake_resolver_public)
    with pytest.raises(NetworkDeny) as exc:
        await g.guarded_request(fetch, "https://ok.test/start")
    assert exc.value.reason in ("ip_interne_bloquee", "domaine_non_autorise", "ssrf_ip_bloquee")


async def test_guarded_request_suit_redirection_ok_et_plafonne():
    async def fetch(url):
        if url == "https://a.test/1":
            return 302, {"location": "https://a.test/2"}, b""
        return 200, {}, b"body"

    g = NetworkGuard(NetworkPolicy(allowed_domains={"a.test"}, min_interval_seconds=0), resolver=_fake_resolver_public)
    status, _, body = await g.guarded_request(fetch, "https://a.test/1")
    assert status == 200 and body == b"body"

    async def fetch_big(url):
        return 200, {}, b"x" * (11 * 1024 * 1024)

    g2 = NetworkGuard(NetworkPolicy(allowed_domains={"a.test"}, min_interval_seconds=0, max_bytes=1024), resolver=_fake_resolver_public)
    with pytest.raises(NetworkDeny) as exc:
        await g2.guarded_request(fetch_big, "https://a.test/big")
    assert exc.value.reason == "taille_depassee"

    async def fetch_loop(url):
        return 302, {"location": url + "x"}, b""

    g3 = NetworkGuard(NetworkPolicy(allowed_domains={"a.test"}, min_interval_seconds=0, max_redirects=2), resolver=_fake_resolver_public)
    with pytest.raises(NetworkDeny) as exc:
        await g3.guarded_request(fetch_loop, "https://a.test/0")
    assert exc.value.reason == "trop_de_redirections"


# ---------- SecretStore (T5.5) ----------

def test_secret_store_memoire_et_persistance_chiffree(tmp_path):
    store = SecretStore(tmp_path, persist=True)
    store.set("api_key_test", "valeur-secrete-123")
    assert store.get("api_key_test") == "valeur-secrete-123"
    assert store.names() == ["api_key_test"]
    # persistance chiffrée : le fichier ne contient jamais la valeur en clair
    enc = tmp_path / "secrets.enc"
    assert enc.exists()
    assert stat.S_IMODE(enc.stat().st_mode) == 0o600
    assert b"valeur-secrete-123" not in enc.read_bytes()
    assert stat.S_IMODE((tmp_path / "secrets.key").stat().st_mode) == 0o600
    # rechargement depuis le disque par une nouvelle instance
    store2 = SecretStore(tmp_path, persist=True)
    assert store2.get("api_key_test") == "valeur-secrete-123"
    assert store2.delete("api_key_test") is True
    assert store2.get("api_key_test") is None


def test_secret_store_sans_persistance(tmp_path):
    store = SecretStore(tmp_path, persist=False)
    store.set("k", "v")
    assert not (tmp_path / "secrets.enc").exists()
    assert SecretStore(tmp_path, persist=False).get("k") is None


def test_secret_store_passphrase_sel_aleatoire_et_rechargement(tmp_path):
    """Correctif d'audit : profil CON-15 — sel Argon2id aléatoire par coffre (pas de sel fixe),
    stocké dans le coffre ; rechargement avec la même passphrase fonctionne."""
    d1, d2 = tmp_path / "a", tmp_path / "b"
    SecretStore(d1, persist=True, passphrase="phrase-secrete").set("k", "v1")
    SecretStore(d2, persist=True, passphrase="phrase-secrete").set("k", "v1")
    b1 = json.loads((d1 / "secrets.enc").read_text())
    b2 = json.loads((d2 / "secrets.enc").read_text())
    assert b1["kdf"]["salt_b64"] != b2["kdf"]["salt_b64"]  # sels distincts
    assert b1["ct"] != b2["ct"]
    assert SecretStore(d1, persist=True, passphrase="phrase-secrete").get("k") == "v1"
    # mauvaise passphrase : lecture vide, sans lever ni fuiter
    assert SecretStore(d1, persist=True, passphrase="mauvaise").get("k") is None


def test_secret_store_illisible_n_est_pas_ecrase(tmp_path):
    """Correctif d'audit : un coffre illisible (corruption/mauvaise passphrase) n'est pas
    silencieusement écrasé par un set() — pas de perte de secrets."""
    store = SecretStore(tmp_path, persist=True)
    store.set("k", "v")
    enc = tmp_path / "secrets.enc"
    original = enc.read_bytes()
    enc.write_bytes(b"corrompu")
    store2 = SecretStore(tmp_path, persist=True)
    assert store2.get("k") is None
    with pytest.raises(ValueError):
        store2.set("k2", "v2")
    assert enc.read_bytes() != original  # toujours le blob corrompu, pas un coffre écrasé
    assert b"corrompu" in enc.read_bytes()


# ---------- Isolation processus (T5.2) ----------

async def test_run_isolated_ok():
    rc, out, _ = await run_isolated(["python3", "-c", "print('ok')"], IsolationLimits(timeout_seconds=10))
    assert rc == 0 and out.strip() == b"ok"


async def test_run_isolated_tue_depassement_cpu():
    """T5.2 : un sous-processus dépassant la limite CPU est tué (SIGXCPU) ou stoppé par le timeout."""
    try:
        rc, _, _ = await run_isolated(
            ["python3", "-c", "while True: pass"],
            IsolationLimits(cpu_seconds=1, timeout_seconds=5),
        )
        assert rc != 0  # returncode négatif = tué par signal (SIGXCPU/SIGKILL)
    except TimeoutError:
        pass  # le timeout a aussi stoppé le processus, c'est conforme


# ---------- Registre / T5.1 ----------

def test_connecteur_experimental_desactive_par_defaut():
    from osia.connectors.registry import ConnectorRegistry

    class Dummy(Connector):
        def __init__(self, trust):
            self.manifest = ConnectorManifest(id="dummy", version="0.1", trust_level=trust, domains=["d.test"])

        async def fetch(self, request):
            raise NotImplementedError

    reg = ConnectorRegistry()
    reg.register(Dummy(TrustLevel.OFFICIAL))
    reg.register(Dummy(TrustLevel.EXPERIMENTAL))
    assert reg.get("dummy") is not None  # id collision, dernier enregistré
    reg2 = ConnectorRegistry()
    reg2.register(Dummy(TrustLevel.EXPERIMENTAL))
    assert reg2.get("dummy") is None  # experimental non activé sans autorisation explicite


# ---------- API CON-06 ----------

async def test_api_net_secrets_connectors(engine):
    async with await client_for(engine) as client:
        r = await client.get("/api/v1/net/policy")
        assert r.status_code == 200
        assert "blocked_networks" in r.json()
        # secrets : noms uniquement, jamais la valeur
        r = await client.put("/api/v1/secrets/ma_cle", json={"value": "valeur-secrete"})
        assert r.status_code == 200
        r = await client.get("/api/v1/secrets")
        assert r.json()["names"] == ["ma_cle"]
        assert "valeur-secrete" not in r.text
        r = await client.delete("/api/v1/secrets/ma_cle")
        assert r.json()["deleted"] is True
        # connecteurs : toggle experimental exige confirm
        r = await client.get("/api/v1/connectors")
        assert r.status_code == 200 and any(c["id"] == "simulated.web" for c in r.json())
        r = await client.post("/api/v1/connectors/simulated.web/toggle", json={"enabled": False})
        assert r.status_code == 200
        # audit : op.secret.set tracé sans la valeur
        entries = engine.audit.read(limit=20)
        assert any(e["action"] == "op.secret.set" for e in entries)
        assert all("valeur-secrete" not in json.dumps(e) for e in entries)


async def test_store_proof_rejette_url_non_http(engine):
    with pytest.raises(ValueError):
        await engine.filestore.store_proof(
            investigation_id="inv_x", content=b"x", source_url="file:///etc/passwd"
        )
