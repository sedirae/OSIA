from __future__ import annotations

import json
import pathlib

import asyncpg

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


async def create_pool(dsn: str, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size)


async def migrate(pool: asyncpg.Pool) -> list[int]:
    applied: list[int] = []
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version integer PRIMARY KEY, name text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        done = {r["version"] for r in rows}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version in done:
                continue
            sql = path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                    version,
                    path.name,
                )
            applied.append(version)
    return applied
