"""Parcours d'installation Linux et base locale dédiée, sans accès réseau externe."""

import importlib.util
import http.client
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time

import pgserver
import pytest


ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("osia_installer", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def install_home(tmp_path, monkeypatch):
    home = tmp_path / "un dossier utilisateur"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    for name, dirname in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                          ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
        monkeypatch.setenv(name, str(home / dirname))
    monkeypatch.delenv("OSIA_DB_DSN", raising=False)
    monkeypatch.delenv("OSIA_INSTALL_BIN_DIR", raising=False)
    monkeypatch.setenv("OSIA_VERSION_CHECK", "0")
    monkeypatch.setattr(installer, "postgres_bin_dir", lambda: pathlib.Path(pgserver.__file__).parent / "pginstall/bin")
    return home


def prepare_virtualenv_without_downloads(monkeypatch):
    """Les dépendances existent déjà dans le venv des tests. Le reste utilise les vrais binaires."""
    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if len(command) >= 4 and command[1:3] == ["-m", "venv"]:
            bindir = pathlib.Path(command[3]) / "bin"
            bindir.mkdir(parents=True)
            python = bindir / "python"
            python.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
            python.chmod(0o755)
            cli = bindir / "osia"
            cli.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m osia \"$@\"\n")
            cli.chmod(0o755)
            return subprocess.CompletedProcess(command, 0)
        if len(command) >= 4 and command[1:4] == ["-m", "pip", "install"]:
            return subprocess.CompletedProcess(command, 0)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)


def test_installation_locale_demarre_et_protege_les_identifiants(install_home, monkeypatch, tmp_path):
    prepare_virtualenv_without_downloads(monkeypatch)
    args = installer.argparse.Namespace(mode="desktop", database="local", web_ui=False)
    installer.install(args)
    launcher = install_home / ".local/bin/osia"
    config_dir = install_home / "config/osia"
    config_file = config_dir / "installation.json"
    secret = config_dir / "database.secret"
    config = json.loads(config_file.read_text())
    assert config["environment"]["OSIA_MODE"] == "desktop"
    assert config["environment"]["OSIA_WEB_UI_ENABLED"] == "0"
    assert secret.read_text().strip().startswith("postgresql://osia:")
    assert secret.read_text().strip() not in config_file.read_text()
    assert secret.stat().st_mode & 0o777 == 0o600
    assert config_file.stat().st_mode & 0o777 == 0o600
    assert subprocess.run([str(launcher), "db", "status"], capture_output=True).returncode == 0
    assert subprocess.run([str(launcher), "version"], capture_output=True).returncode == 0

    try:
        backup_dir = tmp_path / "backup"
        result = subprocess.run([str(launcher), "backup", "create", "--dest", str(backup_dir)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        copies = list(backup_dir.rglob("installation.json"))
        assert copies and not list(backup_dir.rglob("database.secret"))
        assert secret.read_text().strip() not in copies[0].read_text()

        with pytest.raises(installer.InstallError, match="existe déjà"):
            installer.install(args)
        assert subprocess.run([str(launcher), "db", "stop"], capture_output=True).returncode == 0
        assert subprocess.run([str(launcher), "db", "status"], capture_output=True).returncode != 0
        # Une commande ordinaire redémarre PostgreSQL et retrouve les migrations.
        assert subprocess.run([str(launcher), "db", "migrate"], capture_output=True, timeout=30).returncode == 0
        assert subprocess.run([str(launcher), "db", "status"], capture_output=True).returncode == 0

        port = installer.free_port()
        app_env = {**os.environ, "OSIA_LISTEN_PORT": str(port)}
        app = subprocess.Popen([str(launcher)], env=app_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if app.poll() is not None:
                    pytest.fail(f"OSIA s’est arrêté au démarrage : {app.stderr.read().decode()}")
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    connection.request("GET", "/api/v1/health")
                    health = connection.getresponse()
                    body = json.loads(health.read())
                    connection.close()
                    break
                except (ConnectionRefusedError, ConnectionResetError, TimeoutError):
                    time.sleep(0.1)
            else:
                pytest.fail("Le serveur OSIA n’a pas démarré.")
            assert health.status == 200 and body["mode"] == "desktop"
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/")
            response = connection.getresponse()
            assert response.status == 404
            response.read()
            connection.close()
        finally:
            app.terminate()
            app.wait(timeout=15)
    finally:
        subprocess.run([str(launcher), "db", "stop"], capture_output=True)


def test_base_existante_et_configuration_invalide_ne_modifient_rien(install_home, monkeypatch):
    args = installer.argparse.Namespace(mode="server", database="existing", web_ui=True)
    monkeypatch.setenv("OSIA_INSTALL_DB_DSN", "not-a-database-url")
    with pytest.raises(installer.InstallError, match="invalide"):
        installer.install(args)
    assert not (install_home / "data/osia/venv").exists()

    previous = install_home / ".local/bin/osia"
    previous.parent.mkdir(parents=True)
    previous.write_text("existant")
    with pytest.raises(installer.InstallError, match="existe déjà"):
        installer.install(args)
    assert previous.read_text() == "existant"
    socket_dsn = "postgresql://osia@/osia?host=%2Ftmp%2Fpostgres"
    assert installer.validate_dsn(socket_dsn) == socket_dsn


async def test_base_existante_en_mode_serveur_requiert_une_authentification(install_home, monkeypatch, engine):
    prepare_virtualenv_without_downloads(monkeypatch)
    monkeypatch.setenv("OSIA_INSTALL_DB_DSN", engine.settings.db_dsn)
    for name in ("OSIA_DB_DSN", "OSIA_CONFIG_DIR", "OSIA_DATA_DIR", "OSIA_CACHE_DIR", "OSIA_LOG_DIR", "OSIA_BACKUP_DIR"):
        monkeypatch.delenv(name, raising=False)
    installer.install(installer.argparse.Namespace(mode="server", database="existing", web_ui=False))
    launcher = install_home / ".local/bin/osia"
    config_dir = install_home / "config/osia"
    assert json.loads((config_dir / "installation.json").read_text())["postgres"] is None
    port = installer.free_port()
    app = subprocess.Popen([str(launcher)], env={**os.environ, "OSIA_LISTEN_PORT": str(port)},
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if app.poll() is not None:
                pytest.fail(f"OSIA s’est arrêté au démarrage : {app.stderr.read().decode()}")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                connection.request("GET", "/api/v1/health")
                response = connection.getresponse()
                response.read()
                connection.close()
                break
            except (ConnectionRefusedError, ConnectionResetError, TimeoutError):
                time.sleep(0.1)
        else:
            pytest.fail("Le serveur OSIA n’a pas démarré.")
        assert response.status == 401
        token = (config_dir / "auth_token").read_text().strip()
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        connection.request("GET", "/api/v1/health", headers={"Authorization": "Bearer " + token})
        response = connection.getresponse()
        assert response.status == 200 and json.loads(response.read())["mode"] == "server"
        connection.close()
    finally:
        app.terminate()
        app.wait(timeout=15)


def test_echec_pip_permet_de_relancer_sans_effacer_de_donnees(install_home, monkeypatch):
    prepare_virtualenv_without_downloads(monkeypatch)
    run = subprocess.run
    config_dir = install_home / "config/osia"
    config_dir.mkdir(parents=True)
    existing = config_dir / "note.txt"
    existing.write_text("à conserver")

    def fail_download(command, *args, **kwargs):
        if command[1:4] == ["-m", "pip", "install"]:
            raise subprocess.CalledProcessError(1, command)
        return run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_download)
    monkeypatch.setenv("OSIA_INSTALL_DB_DSN", "postgresql://osia@localhost/osia")
    args = installer.argparse.Namespace(mode="desktop", database="existing", web_ui=True)
    for _ in range(2):
        with pytest.raises(subprocess.CalledProcessError):
            installer.install(args)
        assert not (install_home / "data/osia/venv").exists()
        assert existing.read_text() == "à conserver"
        assert not (config_dir / "database.secret").exists()
