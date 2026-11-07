from __future__ import annotations

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
      dans config_dir/secrets.key en 0600, ou passphrase via OSIA_SECRETS_PASSPHRASE).
    - Jamais de valeur en clair sur disque, dans les journaux, les exports ou les prompts :
      seules les noms sont listables.
    """

    def __init__(self, config_dir: pathlib.Path, persist: bool = True, passphrase: Optional[str] = None):
        self.config_dir = pathlib.Path(config_dir)
        self.persist = persist
        self.passphrase = passphrase or os.environ.get("OSIA_SECRETS_PASSPHRASE")
        self._mem: dict[str, str] = {}
        self._key: bytes | None = None
        self._store_path = self.config_dir / "secrets.enc"
        self._key_path = self.config_dir / "secrets.key"

    def _load_key(self) -> bytes:
        if self._key is not None:
            return self._key
        if self.passphrase:
            salt = b"osia-secrets-v1"  # sel fixe : la clé dérive de la passphrase seule
            self._key = ArchiveCrypto.derive_key(self.passphrase, salt)
            return self._key
        if self._key_path.exists():
            self._key = self._key_path.read_bytes()
            return self._key
        key = _secrets.token_bytes(32)
        secure_write(self._key_path, key)
        self._key = key
        return key

    def _load(self) -> None:
        if not self.persist or not self._store_path.exists():
            return
        raw = self._store_path.read_bytes()
        try:
            blob = json.loads(raw.decode("utf-8"))
            nonce = bytes.fromhex(blob["nonce"])
            ct = bytes.fromhex(blob["ct"])
            data = AESGCM(self._load_key()).decrypt(nonce, ct, None)
            self._mem = json.loads(data.decode("utf-8"))
        except Exception:
            # coffre illisible/corrompu : on repart à vide plutôt que de fuiter ou planter
            self._mem = {}

    def _save(self) -> None:
        if not self.persist:
            return
        self.config_dir.mkdir(parents=True, exist_ok=True)
        nonce = _secrets.token_bytes(12)
        ct = AESGCM(self._load_key()).encrypt(nonce, json.dumps(self._mem).encode("utf-8"), None)
        secure_write(self._store_path, json.dumps({"nonce": nonce.hex(), "ct": ct.hex()}))

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
