"""Recette Chromium sur le vrai serveur (activée explicitement dans la CI)."""

import http.client
import os
import pathlib
import secrets
import socket
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(os.environ.get("OSIA_BROWSER_TESTS") != "1", reason="Chromium : recette activée dans la CI")
async def test_browser_server_settings_import_navigation_logout(engine):
    token = secrets.token_urlsafe(24)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {
        **os.environ, "OSIA_MODE": "server", "OSIA_LISTEN_HOST": "127.0.0.1",
        "OSIA_LISTEN_PORT": str(port), "OSIA_AUTH_TOKEN": token, "OSIA_VERSION_CHECK": "0",
        "OSIA_AI_PROVIDER": "simulated", "OSIA_WEB_UI_ENABLED": "1",
    }
    with subprocess.Popen([sys.executable, "-m", "osia", "serve"], env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as server:
        try:
            for _ in range(100):
                if server.poll() is not None:
                    pytest.fail("Le serveur de recette n’a pas démarré : " + server.stderr.read().decode())
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    connection.request("GET", "/")
                    response = connection.getresponse()
                    response.read()
                    connection.close()
                    if response.status == 200:
                        break
                except (OSError, TimeoutError):
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Délai de démarrage dépassé")
            result = subprocess.run(
                ["node", str(pathlib.Path(__file__).with_name("browser_review.cjs")), f"http://127.0.0.1:{port}"],
                env={**os.environ, "OSIA_BROWSER_TOKEN": token}, capture_output=True, text=True, timeout=90,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
