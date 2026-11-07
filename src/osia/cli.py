from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import pathlib
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
    if inv is None:
        print(f"investigation inconnue: {args.id}", file=sys.stderr)
        return 1
    print(json.dumps({"id": inv["id"], "state": inv["state"], "stop_reason": inv["stop_reason"]}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_op_reconcile(args) -> int:
    from .engine import Engine
    from .models import PolicyDeny

    engine = Engine(_settings())
    await engine.setup()
    try:
        op = await engine.policy.reconcile_uncertain(args.id, billed=args.billed, actual_cents=args.actual_cents)
    except PolicyDeny as deny:
        print(f"réconciliation impossible: {deny.reason}", file=sys.stderr)
        await engine.pool.close()
        return 1
    print(json.dumps({"id": op["id"], "state": op["state"]}, ensure_ascii=False))
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


def _passphrase(args) -> str | None:
    """Phrase d'archive : jamais en argument de ligne de commande (historique shell)."""
    return os.environ.get("OSIA_ARCHIVE_PASSPHRASE") or (getpass.getpass("Phrase secrète de l'archive : ") if getattr(args, "encrypt", False) or getattr(args, "need_pass", False) else None)


async def _cmd_export(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    passphrase = _passphrase(args)
    result = await engine.exchange.export_investigation(
        args.id,
        format=args.format,
        branch_ids=args.branch or None,
        include_proofs=not args.no_proofs,
        exclusions=set(args.exclude or []),
        encrypt=args.encrypt,
        passphrase=passphrase,
    )
    out = pathlib.Path(args.out) if args.out else pathlib.Path(result["dir"])
    out.mkdir(parents=True, exist_ok=True)
    src_dir = pathlib.Path(result["dir"])
    for f in result["files"]:
        (out / f["file"]).write_bytes((src_dir / f["file"]).read_bytes())
    print(json.dumps({"export_id": result["export_id"], "format": result["format"], "encrypted": result["encrypted"], "partial": result["partial"], "counts": result["counts"], "warnings": result["warnings"], "out": str(out)}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_import(args) -> int:
    from .engine import Engine
    from .exchange import ArchiveError, CryptoError, ImportConflictError

    engine = Engine(_settings())
    await engine.setup()
    passphrase = os.environ.get("OSIA_ARCHIVE_PASSPHRASE")
    path = pathlib.Path(args.file)
    if args.preview:
        try:
            preview = await engine.exchange.preview_import(path, passphrase)
        except (ArchiveError, CryptoError) as exc:
            print(f"archive invalide: {exc}", file=sys.stderr)
            await engine.pool.close()
            return 1
        print(json.dumps(preview, ensure_ascii=False, default=str))
        await engine.pool.close()
        return 0
    try:
        report = await engine.exchange.apply_import(
            path, mode=args.mode, on_conflict=args.on_conflict, passphrase=passphrase
        )
    except ImportConflictError as exc:
        print(json.dumps({"error": "import_conflict", "conflicts": exc.conflicts}, ensure_ascii=False), file=sys.stderr)
        await engine.pool.close()
        return 2
    except (ArchiveError, CryptoError) as exc:
        print(f"archive invalide: {exc}", file=sys.stderr)
        await engine.pool.close()
        return 1
    print(json.dumps({"applied": True, "mode": report["mode"], "inserted": report["inserted"], "normalized_states": report["normalized_states"], "warnings": report["warnings"]}, ensure_ascii=False, default=str))
    await engine.pool.close()
    return 0


async def _cmd_backup_create(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    result = await engine.backup.create(dest_dir=pathlib.Path(args.dest) if args.dest else None)
    print(json.dumps({"id": result["id"], "dest_dir": result["dest_dir"], "size_bytes": result["size_bytes"], "proof_files": result["manifest"]["counts"]["proof_files"]}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_backup_list(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    for row in await engine.backup.list_backups():
        print(f"{row['id']}\t{row['kind']}\t{row['created_at'].isoformat()}\t{row['dest_dir']}\t{row['size_bytes']}\tverifie={'oui' if row['verified_at'] else 'non'}")
    await engine.pool.close()
    return 0


async def _cmd_backup_verify(args) -> int:
    from .engine import Engine
    from .backup import BackupError

    engine = Engine(_settings())
    await engine.setup()
    try:
        result = await engine.backup.verify(args.id)
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        await engine.pool.close()
        return 1
    print(json.dumps(result, ensure_ascii=False, default=str))
    await engine.pool.close()
    return 0 if result["verified"] else 1


async def _cmd_backup_restore(args) -> int:
    from .engine import Engine
    from .backup import BackupError

    engine = Engine(_settings())
    await engine.setup()
    if not args.yes:
        print("restauration destructive : confirmez avec --yes (une sauvegarde prealable sera creee si la base est non vide)", file=sys.stderr)
        await engine.pool.close()
        return 1
    try:
        result = await engine.backup.restore(args.id, confirm=True, target_dsn=args.target_dsn)
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        await engine.pool.close()
        return 1
    print(json.dumps(result, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_auth_token(args) -> int:
    """CON-05 : affiche le jeton administrateur local (fichier 0600), jamais journalisé."""
    settings = _settings()
    token_file = settings.paths.config_dir / "auth_token"
    if not token_file.exists():
        print("aucun jeton local : démarrez en mode serveur pour en générer un, ou définissez OSIA_AUTH_TOKEN", file=sys.stderr)
        return 1
    print(token_file.read_text(encoding="utf-8").strip())
    return 0


async def _cmd_auth_rotate(args) -> int:
    """CON-05 (T5.7) : rotation du jeton administrateur — nouveau jeton, hash mis à jour,
    toutes les sessions révoquées, événement audité (sans secret)."""
    import secrets

    from .engine import Engine
    from .security import hash_token
    from .config import secure_write

    engine = Engine(_settings())
    await engine.setup()
    token = secrets.token_urlsafe(32)
    await engine.repo.set_setting("auth_token_hash", hash_token(token))
    secure_write(engine.settings.paths.config_dir / "auth_token", token + "\n")
    revoked = await engine.sessions.revoke_all()
    engine.audit.log("auth.token.rotated", "success", detail={"sessions_revoked": revoked})
    print(json.dumps({"rotated": True, "sessions_revoked": revoked}, ensure_ascii=False))
    print("nouveau jeton écrit dans " + str(engine.settings.paths.config_dir / "auth_token") + " (0600)")
    await engine.pool.close()
    return 0


async def _cmd_audit(args) -> int:
    """CON-05 (T5.9) : affiche le journal d'audit de sécurité (déjà sans secrets)."""
    from .security import SecurityAudit

    settings = _settings()
    audit = SecurityAudit(settings.paths.log_dir, retention_days=settings.audit_retention_days)
    for entry in audit.read(limit=args.limit):
        print(json.dumps(entry, ensure_ascii=False))
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
    export = inv_sub.add_parser("export", help="exporter une archive .osia et/ou un rapport HTML (D5, T7)")
    export.add_argument("id")
    export.add_argument("--format", choices=["osia", "html", "both"], default="osia")
    export.add_argument("--out", help="répertoire de sortie (défaut : exports internes)")
    export.add_argument("--branch", action="append", help="restreindre à une branche (répétable)")
    export.add_argument("--no-proofs", action="store_true", help="exclure les binaires des preuves (T7.4)")
    export.add_argument("--exclude", action="append", help="exclure une table technique (tasks, events, ledger, reservations, external_ops)")
    export.add_argument("--encrypt", action="store_true", help="chiffrer l'archive (AES-256-GCM + Argon2id, CON-15)")
    export.set_defaults(func=_cmd_export)

    imp = sub.add_parser("import", help="prévisualiser ou appliquer l'import d'une archive .osia (T7.6)")
    imp.add_argument("file")
    imp.add_argument("--preview", action="store_true", help="prévisualiser sans modifier (conflits, périmètre)")
    imp.add_argument("--mode", choices=["add", "merge"], default="add")
    imp.add_argument("--on-conflict", choices=["fail", "skip"], default="fail")
    imp.set_defaults(func=_cmd_import)

    backup = sub.add_parser("backup", help="sauvegarde technique manuelle à chaud (T2.6, CON-16)")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    bcreate = backup_sub.add_parser("create", help="créer une sauvegarde cohérente à chaud")
    bcreate.add_argument("--dest", help="répertoire destination (défaut : OSIA_BACKUP_DIR)")
    bcreate.set_defaults(func=_cmd_backup_create)
    backup_sub.add_parser("list", help="lister les sauvegardes").set_defaults(func=_cmd_backup_list)
    bverify = backup_sub.add_parser("verify", help="vérifier l'intégrité d'une sauvegarde")
    bverify.add_argument("id")
    bverify.set_defaults(func=_cmd_backup_verify)
    brestore = backup_sub.add_parser("restore", help="restaurer une sauvegarde (destructif, --yes requis)")
    brestore.add_argument("id")
    brestore.add_argument("--yes", action="store_true", help="confirmation explicite requise")
    brestore.add_argument("--target-dsn", help="DSN cible (défaut : base courante)")
    brestore.set_defaults(func=_cmd_backup_restore)

    op = sub.add_parser("op", help="gérer les opérations externes")
    op_sub = op.add_subparsers(dest="op_command", required=True)
    reconcile = op_sub.add_parser("reconcile", help="réconcilier une opération incertaine")
    reconcile.add_argument("id")
    reconcile.add_argument("--billed", action="store_true", help="l'appel a été facturé")
    reconcile.add_argument("--actual-cents", type=int, default=None, help="coût réel en centimes si facturé")
    reconcile.set_defaults(func=_cmd_op_reconcile)

    events = sub.add_parser("events", help="afficher le journal d'une investigation")
    events.add_argument("id")
    events.add_argument("--after", type=int, default=0)
    events.set_defaults(func=_cmd_events)

    auth = sub.add_parser("auth", help="authentification administrateur (mode serveur, CON-05/T5.7)")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("token", help="afficher le jeton administrateur local (fichier 0600)").set_defaults(func=_cmd_auth_token)
    auth_sub.add_parser("rotate", help="générer un nouveau jeton et révoquer toutes les sessions").set_defaults(func=_cmd_auth_rotate)

    audit = sub.add_parser("audit", help="afficher le journal d'audit de sécurité (T5.9, sans secrets)")
    audit.add_argument("--limit", type=int, default=100)
    audit.set_defaults(func=_cmd_audit)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
