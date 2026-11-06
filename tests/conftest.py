import secrets
import tempfile

import asyncpg
import pgserver
import pytest


@pytest.fixture(scope="session")
def pg_server():
    data_dir = tempfile.mkdtemp(prefix="osia-pg-")
    server = pgserver.get_server(data_dir)
    yield server
    server.cleanup()


@pytest.fixture
async def engine(pg_server, tmp_path, monkeypatch):
    dbname = f"osia_t_{secrets.token_hex(4)}"
    admin = await asyncpg.connect(pg_server.get_uri())
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    await admin.close()
    monkeypatch.setenv("OSIA_DB_DSN", pg_server.get_uri(database=dbname))
    monkeypatch.setenv("OSIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OSIA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSIA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("OSIA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OSIA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("OSIA_MODE", raising=False)
    monkeypatch.delenv("OSIA_AUTH_TOKEN", raising=False)
    from osia.config import Settings
    from osia.engine import Engine

    eng = Engine(Settings.from_env())
    await eng.setup()
    yield eng
    await eng.pool.close()
    admin = await asyncpg.connect(pg_server.get_uri())
    await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    await admin.close()


async def make_investigation(engine, **kwargs):
    from osia.models import CreateInvestigationRequest

    kwargs.setdefault("title", "investigation test")
    return await engine.orchestrator.start_investigation(CreateInvestigationRequest(**kwargs))
