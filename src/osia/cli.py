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


async def _cmd_net_policy(args) -> int:
    """CON-06 / T5.4 : affiche la politique réseau effective."""
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    p = engine.netguard.policy
    print(json.dumps({
        "allowed_domains": sorted(p.allowed_domains),
        "denied_domains": sorted(p.denied_domains),
        "max_redirects": p.max_redirects,
        "timeout_seconds": p.timeout_seconds,
        "max_bytes": p.max_bytes,
        "min_interval_seconds": p.min_interval_seconds,
        "blocked_networks": [str(n) for n in p.blocked_networks],
    }, ensure_ascii=False, indent=2))
    await engine.pool.close()
    return 0


async def _cmd_secrets_list(args) -> int:
    from .security import SecretStore

    settings = _settings()
    store = SecretStore(settings.paths.config_dir, persist=settings.secrets_persist)
    for name in store.names():
        print(name)
    return 0


async def _cmd_secrets_set(args) -> int:
    """CON-06 / T5.5 : la valeur passe par variable d'environnement ou prompt, jamais en argument."""
    from .security import SecretStore

    settings = _settings()
    store = SecretStore(settings.paths.config_dir, persist=settings.secrets_persist)
    value = os.environ.get("OSIA_SECRET_VALUE") or getpass.getpass(f"Valeur du secret {args.name} : ")
    store.set(args.name, value)
    print(f"secret enregistré (chiffré si persistance activée) : {args.name}")
    return 0


async def _cmd_secrets_get(args) -> int:
    from .security import SecretStore

    settings = _settings()
    store = SecretStore(settings.paths.config_dir, persist=settings.secrets_persist)
    value = store.get(args.name)
    if value is None:
        print(f"secret inconnu : {args.name}", file=sys.stderr)
        return 1
    print(value)
    return 0


async def _cmd_secrets_delete(args) -> int:
    from .security import SecretStore

    settings = _settings()
    store = SecretStore(settings.paths.config_dir, persist=settings.secrets_persist)
    deleted = store.delete(args.name)
    print(json.dumps({"name": args.name, "deleted": deleted}, ensure_ascii=False))
    return 0 if deleted else 1


async def _cmd_connectors_list(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    for c in engine.registry.list():
        print(f"{c['id']}\t{c['trust_level']}\tenabled={c['enabled']}\tdomains={','.join(c['domains'])}")
    await engine.pool.close()
    return 0


async def _cmd_connector_toggle(args) -> int:
    """CON-06 / T5.1 : --confirm exigé pour activer un connecteur EXPERIMENTAL."""
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    entry = next((c for c in engine.registry.list() if c["id"] == args.id), None)
    if entry is None:
        print(f"connecteur inconnu : {args.id}", file=sys.stderr)
        await engine.pool.close()
        return 1
    if args.enable and entry["trust_level"] == "experimental" and not args.confirm:
        print("connecteur expérimental : --confirm exigé (T5.1)", file=sys.stderr)
        await engine.pool.close()
        return 1
    engine.registry.set_enabled(args.id, args.enable)
    await engine.repo.set_setting(f"allow_experimental:{args.id}", bool(args.enable and entry["trust_level"] == "experimental"))
    if args.enable:
        engine.policy.allow_target(args.id)
    engine.audit.log("op.connector.toggle", "success", detail={"connector_id": args.id, "enabled": args.enable})
    print(json.dumps({"id": args.id, "enabled": args.enable}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_ai_providers(args) -> int:
    """CON-11 / D2 §4.2 : fournisseurs IA enregistrés, modèles par rôle, replis (sans clés)."""
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    roles_by_key: dict[str, list[str]] = {}
    for role, key in engine.broker.role_models.items():
        roles_by_key.setdefault(key, []).append(role)
    for key, ad in engine.broker.adapters.items():
        print(
            f"{key}\t{ad.provider}:{ad.model}\tpaid={ad.paid}\tcost={ad.cost_per_call_cents}\t"
            f"roles={','.join(roles_by_key.get(key, []))}\tfallback_to={engine.broker.allowed_fallbacks.get(key)}"
        )
    await engine.pool.close()
    return 0


async def _cmd_ai_test(args) -> int:
    """CON-11 / D2 §4.2 : test de connexion explicite (GET /models, non facturé ; B6)."""
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    adapter = engine.broker.adapters.get(args.key)
    if adapter is None:
        print(f"fournisseur inconnu : {args.key}", file=sys.stderr)
        await engine.pool.close()
        return 1
    try:
        result = await adapter.ping()
    except Exception as exc:
        engine.audit.log("op.ai.test", "failure", detail={"provider_key": args.key}, client=None)
        print(f"test de connexion échoué : {exc}", file=sys.stderr)
        await engine.pool.close()
        return 1
    engine.audit.log("op.ai.test", "success", detail={"provider_key": args.key}, client=None)
    print(json.dumps(result, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_ai_fallback(args) -> int:
    """CON-11 / T8.8/T8.9 + V1.3 : autorise ou révoque le repli local -> cloud (persisté, audité).
    Le flag --enable/--disable est EXPLICITE : aucune autorisation implicite (T8.9)."""
    if args.enable is None:
        print("préciser --enable ou --disable (aucune autorisation implicite du repli, T8.9)", file=sys.stderr)
        return 2
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    await engine.repo.set_setting("allow_ai_fallback_local_to_cloud", bool(args.enable))
    if args.enable and "local" in engine.broker.adapters and "mistral" in engine.broker.adapters:
        engine.broker.allowed_fallbacks["local"] = "mistral"
    else:
        engine.broker.allowed_fallbacks.pop("local", None)
    engine.audit.log("op.ai.fallback.toggle", "success", detail={"enabled": bool(args.enable)}, client=None)
    print(json.dumps({"allow_ai_fallback_local_to_cloud": bool(args.enable), "fallbacks": dict(engine.broker.allowed_fallbacks)}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_settings_list(args) -> int:
    """CON-13 / D7 §9.1 : paramètres globaux effectifs (clés modifiables, sans secrets)."""
    from .engine import Engine
    from .models import EDITABLE_SETTINGS

    engine = Engine(_settings())
    await engine.setup()
    for key in EDITABLE_SETTINGS:
        print(f"{key}\t{await engine.repo.get_setting(key)}")
    await engine.pool.close()
    return 0


async def _cmd_settings_set(args) -> int:
    """CON-13 / D7 §9.3 : modification validée (avant enregistrement) et auditée d'un paramètre
    global. S'applique aux futures opérations ; pas de rétroactivité (D7 §9.2)."""
    from .engine import Engine
    from .models import validate_setting_value

    raw = args.value
    if raw.lower() in ("true", "false"):
        value: object = raw.lower() == "true"
    else:
        try:
            value = int(raw)
        except ValueError:
            value = raw
    try:
        value = validate_setting_value(args.key, value)
    except ValueError as exc:
        print(f"valeur invalide : {exc}", file=sys.stderr)
        return 1
    engine = Engine(_settings())
    await engine.setup()
    await engine.repo.set_setting(args.key, value)
    if args.key == "audit_retention_days":
        engine.audit.retention_days = int(value)
    if args.key == "session_ttl_hours":
        from datetime import timedelta

        engine.sessions.ttl = timedelta(hours=int(value))
    engine.audit.log("op.settings.update", "success", detail={"keys": [args.key]}, client=None)
    print(json.dumps({"updated": {args.key: value}}, ensure_ascii=False))
    await engine.pool.close()
    return 0


async def _cmd_profiles_list(args) -> int:
    from .engine import Engine

    engine = Engine(_settings())
    await engine.setup()
    for p in await engine.repo.list_profiles():
        print(f"{p['id']}\t{p['name']}\trebonds={p['max_rebonds']}\tsources={p['max_source_requests']}\tai={p['max_ai_calls']}\tduree={p['max_duration_seconds']}s\tcost={p['max_cost_cents']}c\tdefault={p['is_default']}")
    await engine.pool.close()
    return 0


async def _cmd_profiles_create(args) -> int:
    """CON-13 / D3 §5.3 : profil personnalisé, bornes validées (LimitSet + CHECK SQL)."""
    from .engine import Engine
    from .models import LimitSet
    from pydantic import ValidationError

    limits = {
        "max_rebonds": args.max_rebonds,
        "max_source_requests": args.max_source_requests,
        "max_ai_calls": args.max_ai_calls,
        "max_duration_seconds": args.max_duration_seconds,
        "max_cost_cents": args.max_cost_cents,
    }
    try:
        LimitSet(**limits)
    except ValidationError as exc:
        print(f"limites invalides : {exc.errors()}", file=sys.stderr)
        return 1
    engine = Engine(_settings())
    await engine.setup()
    try:
        row = await engine.repo.create_profile(profile_id=args.id, name=args.name, limits=limits, is_default=args.default)
    except Exception as exc:
        print(f"création refusée : {exc}", file=sys.stderr)
        await engine.pool.close()
        return 1
    engine.audit.log("op.profile.create", "success", detail={"profile_id": args.id, "is_default": args.default}, client=None)
    print(json.dumps({"id": row["id"], "name": row["name"], "is_default": row["is_default"]}, ensure_ascii=False))
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

    net = sub.add_parser("net", help="politique réseau centralisée (CON-06, T5.4)")
    net_sub = net.add_subparsers(dest="net_command", required=True)
    net_sub.add_parser("policy", help="afficher la politique réseau effective").set_defaults(func=_cmd_net_policy)

    sec = sub.add_parser("secrets", help="coffre de secrets chiffré (CON-06, T5.5) — jamais de valeur en clair en argument")
    sec_sub = sec.add_subparsers(dest="secrets_command", required=True)
    sec_sub.add_parser("list", help="lister les noms de secrets").set_defaults(func=_cmd_secrets_list)
    sset = sec_sub.add_parser("set", help="enregistrer un secret (env OSIA_SECRET_VALUE ou prompt)")
    sset.add_argument("name")
    sset.set_defaults(func=_cmd_secrets_set)
    sget = sec_sub.add_parser("get", help="afficher un secret (usage local uniquement)")
    sget.add_argument("name")
    sget.set_defaults(func=_cmd_secrets_get)
    sdel = sec_sub.add_parser("delete", help="supprimer un secret")
    sdel.add_argument("name")
    sdel.set_defaults(func=_cmd_secrets_delete)

    conn = sub.add_parser("connectors", help="connecteurs enregistrés (CON-06, T5.1)")
    conn_sub = conn.add_subparsers(dest="connectors_command", required=True)
    conn_sub.add_parser("list", help="lister les connecteurs et leur niveau de confiance").set_defaults(func=_cmd_connectors_list)
    ctoggle = conn_sub.add_parser("toggle", help="activer/désactiver un connecteur (--confirm pour experimental)")
    ctoggle.add_argument("id")
    ctoggle.add_argument("--enable", action="store_true", default=True)
    ctoggle.add_argument("--disable", dest="enable", action="store_false")
    ctoggle.add_argument("--confirm", action="store_true", help="autorisation explicite requise pour un connecteur expérimental (T5.1)")
    ctoggle.set_defaults(func=_cmd_connector_toggle)

    ai = sub.add_parser("ai", help="courtier IA : fournisseurs, modèles par rôle, repli (CON-11, T8/D2)")
    ai_sub = ai.add_subparsers(dest="ai_command", required=True)
    ai_sub.add_parser("providers", help="lister les fournisseurs IA enregistrés (sans clés)").set_defaults(func=_cmd_ai_providers)
    aitest = ai_sub.add_parser("test", help="tester la connexion d'un fournisseur (GET /models, non facturé)")
    aitest.add_argument("key")
    aitest.set_defaults(func=_cmd_ai_test)
    aifb = ai_sub.add_parser("fallback", help="autoriser/révoquer le repli local -> cloud (T8.9, V1.3)")
    aifb.add_argument("--enable", dest="enable", action="store_true", default=None)
    aifb.add_argument("--disable", dest="enable", action="store_false", default=None)
    aifb.set_defaults(func=_cmd_ai_fallback)

    st = sub.add_parser("settings", help="paramètres globaux hiérarchisés (CON-13, D7 §9.1-9.3) — sans secrets")
    st_sub = st.add_subparsers(dest="settings_command", required=True)
    st_sub.add_parser("list", help="afficher les paramètres globaux effectifs").set_defaults(func=_cmd_settings_list)
    sset2 = st_sub.add_parser("set", help="modifier un paramètre (validé avant enregistrement, D7 §9.3)")
    sset2.add_argument("key")
    sset2.add_argument("value")
    sset2.set_defaults(func=_cmd_settings_set)

    prof = sub.add_parser("profiles", help="profils de recherche (CON-13, D3 §5.3, V1.4)")
    prof_sub = prof.add_subparsers(dest="profiles_command", required=True)
    prof_sub.add_parser("list", help="lister les profils").set_defaults(func=_cmd_profiles_list)
    pcreate = prof_sub.add_parser("create", help="créer un profil personnalisé (bornes validées)")
    pcreate.add_argument("--id", required=True)
    pcreate.add_argument("--name", required=True)
    pcreate.add_argument("--max-rebonds", type=int, required=True)
    pcreate.add_argument("--max-source-requests", type=int, required=True)
    pcreate.add_argument("--max-ai-calls", type=int, required=True)
    pcreate.add_argument("--max-duration-seconds", type=int, required=True)
    pcreate.add_argument("--max-cost-cents", type=int, required=True)
    pcreate.add_argument("--default", action="store_true")
    pcreate.set_defaults(func=_cmd_profiles_create)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
