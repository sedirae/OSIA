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
    try:
        await ensure_server_credentials(engine)
        recovery = await engine.start()
        if settings.version_check_enabled:
            # EXEC-06 : notification de version au démarrage — best-effort, ne lève jamais,
            # et en TÂCHE DE FOND (audit PR#25 P3-2) : un réseau lent ne doit pas retarder
            # l'écoute du serveur.
            from .version import fetch_latest_version, is_newer, __version__

            async def _version_check() -> None:
                engine.latest_version = await fetch_latest_version(url=settings.version_check_url)
                engine.techlog.log(
                    "version.check",
                    "version.check",
                    detail={
                        "current": __version__,
                        "latest": engine.latest_version,
                        "update_available": is_newer(engine.latest_version),
                    },
                )

            engine._version_check_task = asyncio.create_task(_version_check())
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
        await server.serve()
    finally:
        await engine.stop()
