from __future__ import annotations

import base64
import json
import os
import pathlib
import secrets as _secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import secure_write
from ..exchange.crypto import ArchiveCrypto


class SecretStore:
    """Gestion centralisée des secrets (T5.5).

    - Secrets gardés en mémoire ; persistance **chiffrée** facultative (AES-256-GCM, clé locale
      dans config_dir/secrets.key en 0600, ou passphrase via OSIA_SECRETS_PASSPHRASE dérivée
      par Argon2id avec sel aléatoire stocké dans le coffre — même profil que CON-15).
    - Jamais de valeur en clair sur disque, dans les journaux, les exports ou les prompts :
      seules les noms sont listables.
    """

    def __init__(self, config_dir: pathlib.Path, persist: bool = True, passphrase: Optional[str] = None):
        self.config_dir = pathlib.Path(config_dir)
        self.persist = persist
        self.passphrase = passphrase or os.environ.get("OSIA_SECRETS_PASSPHRASE")
        self._mem: dict[str, str] = {}
        self._key: bytes | None = None
        self._salt: bytes | None = None
        self._corrupt = False
        self._store_path = self.config_dir / "secrets.enc"
        self._key_path = self.config_dir / "secrets.key"

    def _vault_key(self, blob: dict | None = None) -> bytes:
        """Clé du coffre : Argon2id sur la passphrase (sel aléatoire persisté dans le coffre,
        profil CON-15) ou clé locale aléatoire (secrets.key, 0600)."""
        if self._key is not None:
            return self._key
        if self.passphrase:
            if self._salt is None:
                kdf = (blob or {}).get("kdf") or {}
                salt_b64 = kdf.get("salt_b64")
                self._salt = base64.b64decode(salt_b64) if salt_b64 else _secrets.token_bytes(16)
            self._key = ArchiveCrypto.derive_key(self.passphrase, self._salt)
        elif self._key_path.exists():
            self._key = self._key_path.read_bytes()
        else:
            self._key = _secrets.token_bytes(32)
            secure_write(self._key_path, self._key)
        return self._key

    def _load(self) -> None:
        if not self.persist or not self._store_path.exists():
            return
        raw = self._store_path.read_bytes()
        try:
            blob = json.loads(raw.decode("utf-8"))
            nonce = bytes.fromhex(blob["nonce"])
            ct = bytes.fromhex(blob["ct"])
            data = AESGCM(self._vault_key(blob)).decrypt(nonce, ct, None)
            self._mem = json.loads(data.decode("utf-8"))
            self._corrupt = False
        except Exception:
            # coffre illisible (mauvaise passphrase, corruption) : les lectures repartent à
            # vide sans fuiter ni planter, mais on refuse ensuite de l'écraser (T5.5).
            self._mem = {}
            self._corrupt = True

    def _save(self) -> None:
        if not self.persist:
            return
        if self._corrupt and self._store_path.exists():
            raise ValueError("coffre de secrets illisible : refus de l'écraser (T5.5)")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        nonce = _secrets.token_bytes(12)
        key = self._vault_key()
        ct = AESGCM(key).encrypt(nonce, json.dumps(self._mem).encode("utf-8"), None)
        blob = {"nonce": nonce.hex(), "ct": ct.hex()}
        if self.passphrase:
            blob["kdf"] = ArchiveCrypto.kdf_params(self._salt or b"")
        secure_write(self._store_path, json.dumps(blob))

    def set(self, name: str, value: str) -> None:
        self._load()
        self._mem[name] = value
        self._save()

    def get(self, name: str) -> Optional[str]:
        self._load()
        return self._mem.get(name)

    def delete(self, name: str) -> bool:
        self._load()
        existed = name in self._mem
        self._mem.pop(name, None)
        if existed:
            self._save()
        return existed

    def names(self) -> list[str]:
        self._load()
        return sorted(self._mem)
