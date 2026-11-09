#!/usr/bin/env python3
"""Installation interactive d'OSIA dans les répertoires de l'utilisateur Linux."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, quote, urlsplit

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from osia.installation import postgres_action  # noqa: E402


class InstallError(Exception):
    pass


def choose(prompt: str, values: dict[str, str], default: str) -> str:
    while True:
        try:
            answer = input(prompt).strip().lower() or default
        except EOFError:
            raise InstallError("Réponse manquante. Utilise --help pour une installation non interactive.") from None
        if answer in values:
            return values[answer]
        print("Réponse non reconnue.")


def postgres_bin_dir() -> pathlib.Path:
    candidates = []
    if shutil.which("pg_config"):
        result = subprocess.run(["pg_config", "--bindir"], capture_output=True, text=True)
        if result.returncode == 0:
            candidates.append(pathlib.Path(result.stdout.strip()))
    if shutil.which("initdb"):
        candidates.append(pathlib.Path(shutil.which("initdb")).resolve().parent)
    candidates.extend(sorted(pathlib.Path("/usr/lib/postgresql").glob("*/bin"), reverse=True))
    candidates.extend(sorted(pathlib.Path("/usr").glob("pgsql-*/bin"), reverse=True))
    for directory in candidates:
        if all((directory / binary).is_file() and os.access(directory / binary, os.X_OK)
               for binary in ("initdb", "pg_ctl", "createdb", "pg_dump", "psql")):
            return directory.resolve()
    raise InstallError(
        "PostgreSQL serveur et ses outils sont requis pour la base locale. "
        "Sous Debian/Ubuntu : sudo apt install postgresql postgresql-client python3-venv. "
        "Sous Fedora : sudo dnf install postgresql-server postgresql python3. "
        "Relance ensuite l’installation."
    )


def private_dir(path: pathlib.Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def write_private(path: pathlib.Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_postgres(directory: pathlib.Path, bin_dir: pathlib.Path, config_dir: pathlib.Path) -> tuple[dict, str, str]:
    if directory.exists():
        raise InstallError(f"Le répertoire PostgreSQL existe déjà : {directory}. Aucune donnée n’a été modifiée.")
    password = secrets.token_urlsafe(32)
    port = free_port()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config_dir, prefix=".pg-password-", delete=False) as handle:
        password_file = pathlib.Path(handle.name)
        handle.write(password + "\n")
    try:
        subprocess.run(
            [str(bin_dir / "initdb"), "-D", str(directory), "-U", "osia", "--auth=scram-sha-256",
             "--pwfile", str(password_file), "--encoding=UTF8"],
            check=True, stdout=subprocess.DEVNULL,
        )
    finally:
        password_file.unlink(missing_ok=True)
    postgres = {
        "bin_dir": str(bin_dir), "data_dir": str(directory), "port": port,
        "log_file": str(directory.parent / "postgres.log"),
    }
    dsn = f"postgresql://osia:{quote(password, safe='')}@127.0.0.1:{port}/osia"
    return postgres, dsn, password


def validate_dsn(value: str) -> str:
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        valid = parsed.scheme in ("postgres", "postgresql") and bool(parsed.path.strip("/") or query.get("dbname"))
        parsed.hostname
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise InstallError("Adresse PostgreSQL invalide. Indique une URL postgresql:// avec hôte et nom de base.")
    return value


def install(args: argparse.Namespace) -> None:
    if sys.platform != "linux" or sys.version_info < (3, 11):
        raise InstallError("OSIA nécessite Linux et Python 3.11 ou plus récent.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise InstallError("Lance l’installation avec ton compte utilisateur, sans sudo.")
    mode = args.mode or choose("Mode [1] Desktop / [2] Server (1) : ", {"1": "desktop", "2": "server"}, "1")
    database = args.database or choose("Base [1] locale dédiée / [2] PostgreSQL existant (1) : ", {"1": "local", "2": "existing"}, "1")
    if args.web_ui is None:
        web_ui = choose("Activer l’interface web ? [O/n] : ", {"o": "yes", "oui": "yes", "n": "no", "non": "no"}, "o") == "yes"
    else:
        web_ui = args.web_ui

    home = pathlib.Path.home()
    config_dir = (pathlib.Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "osia").resolve()
    data_dir = (pathlib.Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "osia").resolve()
    cache_dir = (pathlib.Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "osia").resolve()
    state_dir = (pathlib.Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "osia").resolve()
    bin_dir = pathlib.Path(os.environ.get("OSIA_INSTALL_BIN_DIR", home / ".local/bin")).resolve()
    config_file = config_dir / "installation.json"
    dsn_file = config_dir / "database.secret"
    venv = data_dir / "venv"
    launcher = bin_dir / "osia"
    for path in (config_file, dsn_file, venv, launcher):
        if path.exists() or path.is_symlink():
            raise InstallError(f"Le chemin {path} existe déjà. L’installation ne l’écrase pas.")

    dsn = ""
    pg_bin = None
    if database == "existing":
        dsn = os.environ.get("OSIA_INSTALL_DB_DSN", "")
        if not dsn:
            if not sys.stdin.isatty():
                raise InstallError("Définis OSIA_INSTALL_DB_DSN pour la base existante.")
            dsn = getpass.getpass("Adresse PostgreSQL (saisie masquée) : ")
        dsn = validate_dsn(dsn)
    else:
        pg_bin = postgres_bin_dir()
        if (data_dir / "postgres").exists():
            raise InstallError(f"Le répertoire {data_dir / 'postgres'} existe déjà. Aucune donnée n’a été modifiée.")

    for directory in (config_dir, data_dir, cache_dir, state_dir, data_dir / "backups"):
        private_dir(directory)
    bin_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    print("Installation d’OSIA et de ses dépendances Python…", flush=True)
    # Le répertoire a été vérifié absent : en cas de réseau coupé/venv incomplet,
    # supprimer uniquement cet environnement neuf pour permettre une nouvelle tentative.
    venv.mkdir(mode=0o700)
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        subprocess.run([str(venv / "bin/python"), "-m", "pip", "install", str(ROOT)], check=True)
    except BaseException:
        shutil.rmtree(venv)
        raise

    postgres = None
    try:
        if pg_bin is not None:
            print("Création de la base PostgreSQL locale…", flush=True)
            postgres, dsn, password = init_postgres(data_dir / "postgres", pg_bin, config_dir)
        write_private(dsn_file, dsn + "\n")
        if postgres:
            if postgres_action(postgres, "start") != 0:
                raise InstallError("Le démarrage de PostgreSQL a échoué. Vérifie le journal postgres.log.")
            pg_env = {**os.environ, "PGPASSWORD": password}
            subprocess.run(
                [str(pg_bin / "createdb"), "-h", "127.0.0.1", "-p", str(postgres["port"]), "-U", "osia", "osia"],
                check=True, env=pg_env,
            )
        environment = {
            "OSIA_MODE": mode, "OSIA_WEB_UI_ENABLED": "1" if web_ui else "0",
            "OSIA_CONFIG_DIR": str(config_dir), "OSIA_DATA_DIR": str(data_dir),
            "OSIA_CACHE_DIR": str(cache_dir), "OSIA_LOG_DIR": str(state_dir / "logs"),
            "OSIA_BACKUP_DIR": str(data_dir / "backups"),
        }
        app_env = {**os.environ, **environment, "OSIA_DB_DSN": dsn}
        if pg_bin:
            app_env["PATH"] = str(pg_bin) + os.pathsep + app_env.get("PATH", "")
        cli = str(venv / "bin/osia")
        print("Initialisation et migration de la base…", flush=True)
        subprocess.run([cli, "init"], check=True, env=app_env)
        migration = subprocess.run([cli, "db", "migrate"], env=app_env, capture_output=True, text=True)
        if migration.returncode:
            raise InstallError("Connexion ou migration PostgreSQL impossible. Vérifie l’adresse et les droits de la base.")
        config = {"version": 1, "venv_dir": str(venv), "environment": environment,
                  "dsn_file": str(dsn_file), "postgres": postgres}
        write_private(config_file, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        command = f"{shlex.quote(str(venv / 'bin/python'))} -m osia.installation {shlex.quote(str(config_file))} \"$@\""
        fd = os.open(launcher, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"#!/bin/sh\nexec {command}\n")
    except BaseException:
        try:
            if postgres and subprocess.run(
                [str(pathlib.Path(postgres["bin_dir"]) / "pg_ctl"), "-D", postgres["data_dir"], "status"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0:
                postgres_action(postgres, "stop")
        except OSError:
            pass
        raise
    print(f"\nInstallation terminée. Lance OSIA avec : {launcher}")
    if web_ui:
        print("Puis ouvre http://127.0.0.1:8471 dans ton navigateur.")
    if mode == "server":
        print(f"Après le premier démarrage, affiche le jeton avec : {launcher} auth token")
    if postgres:
        print(f"Base locale : démarre automatiquement. Pour l’arrêter : {launcher} db stop")


def main() -> int:
    parser = argparse.ArgumentParser(description="Installation guidée d’OSIA pour l’utilisateur Linux")
    parser.add_argument("--mode", choices=("desktop", "server"))
    parser.add_argument("--database", choices=("local", "existing"))
    web = parser.add_mutually_exclusive_group()
    web.add_argument("--web", dest="web_ui", action="store_true")
    web.add_argument("--no-web", dest="web_ui", action="store_false")
    parser.set_defaults(web_ui=None)
    args = parser.parse_args()
    try:
        install(args)
    except (InstallError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Installation interrompue : {exc}", file=sys.stderr)
        print("Une installation incomplète peut subsister dans les répertoires OSIA. Vérifie-les avant de relancer.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInstallation interrompue. Vérifie les répertoires OSIA avant de relancer.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
