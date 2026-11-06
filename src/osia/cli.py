from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import Settings


def _settings() -> Settings:
    return Settings.from_env()


async def _cmd_init(args) -> int:
    settings = _settings()
    settings.paths.ensure()
    print(f"arborescence initialisée: {settings.paths.data_dir}")
    return 0


async def _cmd_db_migrate(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    print("migrations appliquées")
    await engine.pool.close()
    return 0


async def _cmd_serve(args) -> int:
    from .server import run_server

    await run_server(_settings())
    return 0


async def _cmd_investigation_start(args) -> int:
    from .engine import Engine
    from .models import CreateInvestigationRequest

    engine = Engine(_settings())
    await engine.setup()
    await engine.start()
    req = CreateInvestigationRequest(
        title=args.title,
        objective=args.objective,
        hints=args.hint or [],
        profile_id=args.profile,
        idempotency_key=args.idempotency_key,
    )
    inv = await engine.orchestrator.start_investigation(req)
    print(json.dumps({"id": inv["id"], "state": inv["state"]}, ensure_ascii=False))
    if args.wait:
        while True:
            await asyncio.sleep(0.2)
            inv = await engine.repo.get_investigation(inv["id"])
            if inv["state"] in ("stopped", "error"):
                break
        print(json.dumps({"id": inv["id"], "state": inv["state"], "stop_reason": inv["stop_reason"]}, ensure_ascii=False))
    await engine.stop()
    return 0


async def _cmd_investigation_list(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    rows = await engine.repo.list_investigations()
    for row in rows:
        print(f"{row['id']}\t{row['state']}\t{row['stop_reason'] or ''}\t{row['title']}")
    await engine.pool.close()
    return 0


async def _cmd_investigation_stop(args) -> int:
    from .engine import Engine
    from .models import StopReason

    engine = Engine(_settings())
    await engine.setup()
    inv = await engine.orchestrator.stop(args.id, StopReason.USER)
    print(json.dumps({"id": inv["id"], "state": inv["state"], "stop_reason": inv["stop_reason"]}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_events(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    events = await engine.repo.list_events(args.id, after_id=args.after)
    for event in events:
        print(f"{event.id}\t{event.type}\t{json.dumps(event.payload, ensure_ascii=False)}")
    await engine.pool.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osia", description="OSIA — moteur d'investigation OSINT")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="créer l'arborescence de données").set_defaults(func=_cmd_init)
    db = sub.add_parser("db", help="administration de la base")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("migrate", help="appliquer les migrations").set_defaults(func=_cmd_db_migrate)

    serve = sub.add_parser("serve", help="démarrer le moteur et l'API")
    serve.set_defaults(func=_cmd_serve)

    inv = sub.add_parser("investigation", help="gérer les investigations")
    inv_sub = inv.add_subparsers(dest="inv_command", required=True)
    start = inv_sub.add_parser("start", help="créer et lancer une investigation")
    start.add_argument("--title", required=True)
    start.add_argument("--objective")
    start.add_argument("--hint", action="append")
    start.add_argument("--profile", default="rapide")
    start.add_argument("--idempotency-key")
    start.add_argument("--wait", action="store_true", help="attendre la fin de l'investigation")
    start.set_defaults(func=_cmd_investigation_start)
    inv_sub.add_parser("list", help="lister les investigations").set_defaults(func=_cmd_investigation_list)
    stop = inv_sub.add_parser("stop", help="arrêter une investigation")
    stop.add_argument("id")
    stop.set_defaults(func=_cmd_investigation_stop)

    events = sub.add_parser("events", help="afficher le journal d'une investigation")
    events.add_argument("id")
    events.add_argument("--after", type=int, default=0)
    events.set_defaults(func=_cmd_events)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
