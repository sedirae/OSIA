from __future__ import annotations

import base64
import os

from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KDF_ALGO = "argon2id"
CIPHER = "AES-256-GCM"
KDF_TIME_COST = 3
KDF_MEMORY_COST = 65536
KDF_PARALLELISM = 4
KDF_HASH_LEN = 32
SALT_BYTES = 16
NONCE_BYTES = 12


class CryptoError(Exception):
    """Echec controle au chiffrement/dechiffrement (mauvais mot de passe, contenu altere)."""


class ArchiveCrypto:
    """Profil cryptographique des archives .osia (CON-15, T7.3) :
    AES-256-GCM authentifie, cle 32 o derivee par Argon2id, sel/nonce aleatoires par archive.
    La phrase secrete n'est jamais stockee dans l'archive."""

    def __init__(self, passphrase: str | None = None):
        self._passphrase = passphrase

    @staticmethod
    def new_salt() -> bytes:
        return os.urandom(SALT_BYTES)

    @staticmethod
    def kdf_params(salt: bytes) -> dict:
        return {
            "algo": KDF_ALGO,
            "time_cost": KDF_TIME_COST,
            "memory_cost": KDF_MEMORY_COST,
            "parallelism": KDF_PARALLELISM,
            "hash_len": KDF_HASH_LEN,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        }

    @staticmethod
    def derive_key(passphrase: str, salt: bytes) -> bytes:
        return hash_secret_raw(
            passphrase.encode("utf-8"),
            salt,
            time_cost=KDF_TIME_COST,
            memory_cost=KDF_MEMORY_COST,
            parallelism=KDF_PARALLELISM,
            hash_len=KDF_HASH_LEN,
            type=Argon2Type.ID,
        )

    def encrypt(self, plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(key).encrypt(nonce, plaintext, None)
        return nonce, ct

    def decrypt(self, nonce: bytes, ciphertext: bytes, key: bytes) -> bytes:
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise CryptoError("dechiffrement impossible (phrase incorrecte ou contenu altere)") from exc

    def key_from_params(self, passphrase: str | None, params: dict) -> bytes:
        phrase = passphrase if passphrase is not None else self._passphrase
        if not phrase:
            raise CryptoError("phrase secrete requise pour une archive chiffree")
        salt = base64.b64decode(params["salt_b64"])
        return self.derive_key(phrase, salt)
