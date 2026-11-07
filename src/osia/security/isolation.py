from __future__ import annotations

import asyncio
import resource
import subprocess
from dataclasses import dataclass


@dataclass
class IsolationLimits:
    """Limites appliquées à un sous-processus (T5.2 : permissions minimales, limites CPU/mémoire,
    restrictions fichiers). Un simple sous-processus n'est PAS une sandbox contre du code hostile
    (T5.2) : ces limites bornent les dégâts, elles ne remplacent pas un conteneur pour les
    connecteurs non fiables."""

    cpu_seconds: int = 10
    memory_bytes: int = 512 * 1024 * 1024
    max_open_files: int = 64
    max_file_size_bytes: int = 100 * 1024 * 1024
    timeout_seconds: float = 30.0


def _apply_rlimits(limits: IsolationLimits) -> None:
    """preexec_fn : applique les rlimits dans l'enfant avant exec."""
    resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_file_size_bytes, limits.max_file_size_bytes))


async def run_isolated(cmd: list[str], limits: IsolationLimits | None = None, cwd: str | None = None) -> tuple[int, bytes, bytes]:
    """Exécute `cmd` dans un sous-processus avec rlimits (T5.2) et un timeout.

    Retourne (returncode, stdout, stderr). Un dépassement de timeout tue le processus."""
    limits = limits or IsolationLimits()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        preexec_fn=lambda: _apply_rlimits(limits),
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=limits.timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"processus isolé dépassant {limits.timeout_seconds}s tué: {cmd[0]}")
    return proc.returncode or 0, out or b"", err or b""


def run_isolated_sync(cmd: list[str], limits: IsolationLimits | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Variante synchrone (CLI) avec les mêmes rlimits."""
    limits = limits or IsolationLimits()
    return subprocess.run(
        cmd,
        capture_output=True,
        timeout=limits.timeout_seconds,
        cwd=cwd,
        preexec_fn=lambda: _apply_rlimits(limits),
    )
