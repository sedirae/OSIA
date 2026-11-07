from __future__ import annotations

import secrets

from ..config import secure_write
from .audit import SecurityAudit
from .sessions import SessionManager, hash_token
from .tls import ensure_self_signed_cert

__all__ = ["SecurityAudit", "SessionManager", "hash_token", "ensure_self_signed_cert", "ensure_server_credentials"]


async def ensure_server_credentials(engine) -> str | None:
    """Mode serveur : si aucun jeton administrateur n'est configuré, en générer un.

    Le hash SHA-256 est stocké en base (setting auth_token_hash) ; le jeton en clair est
    écrit une seule fois dans config_dir/auth_token (0600). Jamais journalisé (T5.9)."""
    settings = engine.settings
    if settings.mode != "server":
        return None
    existing = settings.auth_token_hash or await engine.repo.get_setting("auth_token_hash")
    if existing in (None, "", "null"):
        existing = None
    if existing:
        return None
    token = secrets.token_urlsafe(32)
    await engine.repo.set_setting("auth_token_hash", hash_token(token))
    secure_write(settings.paths.config_dir / "auth_token", token + "\n")
    engine.audit.log("auth.token.issued", "success", detail={"mode": "server"})
    return token
