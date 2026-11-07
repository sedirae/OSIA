from __future__ import annotations

import asyncio

import uvicorn

from .api import create_app
from .config import Settings, is_local_host
from .engine import Engine
from .security import ensure_self_signed_cert, ensure_server_credentials


async def run_server(settings: Settings) -> None:
    # CON-05 (T1/T5.7) : refuse toute exposition distante implicite ou non chiffrée.
    settings.validate_runtime()
    engine = Engine(settings)
    await engine.setup()
    await ensure_server_credentials(engine)
    recovery = await engine.start()
    app = create_app(engine)
    ssl_certfile = ssl_keyfile = None
    if settings.tls_enabled:
        ssl_certfile, ssl_keyfile = settings.tls_certfile, settings.tls_keyfile
    elif settings.mode == "server" and settings.tls_autogen and not is_local_host(settings.listen_host):
        cert, key = ensure_self_signed_cert(settings.paths.config_dir / "tls")
        ssl_certfile, ssl_keyfile = str(cert), str(key)
    config = uvicorn.Config(
        app,
        host=settings.listen_host,
        port=settings.listen_port,
        log_level="warning",
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await engine.stop()
