"""Lanceur d'une installation utilisateur et de sa base PostgreSQL locale facultative."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


def postgres_action(postgres: dict, action: str) -> int:
    pg_ctl = pathlib.Path(postgres["bin_dir"]) / "pg_ctl"
    command = [str(pg_ctl), "-D", postgres["data_dir"]]
    if action == "start":
        status = subprocess.run(command + ["status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if status.returncode == 0:
            return 0
        if status.returncode != 3:
            print("Impossible de vérifier l’état de PostgreSQL.", file=sys.stderr)
            return status.returncode
        options = f"-h 127.0.0.1 -p {int(postgres['port'])} -c unix_socket_directories=''"
        command += ["-l", postgres["log_file"], "-o", options, "-w", "start"]
    elif action == "stop":
        command += ["-m", "fast", "-w", "stop"]
    else:
        command += ["status"]
    return subprocess.run(command).returncode


def launch(config_path: pathlib.Path, args: list[str]) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("version") != 1:
        raise ValueError("Version de configuration d’installation non reconnue.")
    for key, value in config["environment"].items():
        os.environ.setdefault(key, value)
    managed_dsn = pathlib.Path(config["dsn_file"]).read_text(encoding="utf-8").strip()
    os.environ.setdefault("OSIA_DB_DSN", managed_dsn)
    postgres = config.get("postgres")
    if postgres:
        os.environ["PATH"] = postgres["bin_dir"] + os.pathsep + os.environ.get("PATH", "")
        if len(args) == 2 and args[0] == "db" and args[1] in ("start", "stop", "status"):
            return postgres_action(postgres, args[1])
        needs_db = not args or args[0] not in ("init", "version", "--help", "-h")
        if needs_db and os.environ.get("OSIA_DB_DSN") == managed_dsn:
            result = postgres_action(postgres, "start")
            if result:
                return result
    cli = pathlib.Path(config["venv_dir"]) / "bin" / "osia"
    os.execv(str(cli), [str(cli), *(args or ["serve"])])
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("Configuration d’installation manquante.", file=sys.stderr)
        return 2
    try:
        return launch(pathlib.Path(sys.argv[1]), sys.argv[2:])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"Impossible de démarrer OSIA : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
