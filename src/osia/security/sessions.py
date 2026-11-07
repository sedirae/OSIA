from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import asyncpg

from ..ids import new_id


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionManager:
    """Sessions serveur (T5.7) : jetons opaques préfixés `sess_`, hashés en base (SHA-256),
    expirables (TTL configurable) et révocables individuellement ou en masse."""

    def __init__(self, pool: asyncpg.Pool, ttl_hours: int = 8):
        self.pool = pool
        self.ttl = timedelta(hours=ttl_hours)

    async def create(self, *, client_info: str | None = None) -> tuple[str, datetime]:
        token = "sess_" + secrets.token_hex(32)
        now = datetime.now(timezone.utc)
        expires = now + self.ttl
        await self.pool.execute(
            "INSERT INTO sessions (id, token_hash, created_at, expires_at, client_info) VALUES ($1, $2, $3, $4, $5)",
            new_id("sess"),
            hash_token(token),
            now,
            expires,
            client_info,
        )
        return token, expires

    async def validate(self, token: str) -> bool:
        row = await self.pool.fetchrow(
            "SELECT expires_at, revoked_at FROM sessions WHERE token_hash = $1", hash_token(token)
        )
        if row is None or row["revoked_at"] is not None:
            return False
        if row["expires_at"] <= datetime.now(timezone.utc):
            return False
        await self.pool.execute("UPDATE sessions SET last_used_at = now() WHERE token_hash = $1", hash_token(token))
        return True

    async def revoke(self, token: str) -> bool:
        cur = await self.pool.execute(
            "UPDATE sessions SET revoked_at = now() WHERE token_hash = $1 AND revoked_at IS NULL",
            hash_token(token),
        )
        return cur == "UPDATE 1"  # token_hash UNIQUE : au plus une session révoquée

    async def revoke_all(self) -> int:
        cur = await self.pool.execute("UPDATE sessions SET revoked_at = now() WHERE revoked_at IS NULL")
        return int(cur.split()[-1])

    async def list_active(self) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT id, created_at, expires_at, last_used_at, client_info FROM sessions "
            "WHERE revoked_at IS NULL AND expires_at > now() ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]
