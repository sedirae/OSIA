from __future__ import annotations

import datetime
import ipaddress
import os
import pathlib

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_self_signed_cert(
    directory: pathlib.Path, common_name: str = "osia.local", days: int = 365
) -> tuple[pathlib.Path, pathlib.Path]:
    """Certificat auto-signé local pour HTTPS (T5.7 : HTTPS obligatoire pour les accès distants).

    Retourne (cert, key). Répertoire 0700, fichiers 0600. Aucun secret n'est transmis au réseau."""
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    key_path = directory / "osia-key.pem"
    cert_path = directory / "osia-cert.pem"
    if key_path.exists() and cert_path.exists():
        return cert_path, key_path
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(common_name), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o600)
    return cert_path, key_path
