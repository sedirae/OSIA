from __future__ import annotations

import asyncio

import uvicorn

from .api import create_app
from .config import Settings
from .engine import Engine


async def run_server(settings: Settings) -> None:
    engine = Engine(settings)
    await engine.setup()
    recovery = await engine.start()
    app = create_app(engine)
    config = uvicorn.Config(app, host=settings.listen_host, port=settings.listen_port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await engine.stop()
