"""Extraction de texte PDF en sous-processus isolé (T5.2, audit issue #17 F02).

`python -m osia.security.pdftool` lit un document PDF sur l'entrée standard et écrit le texte
extrait sur la sortie standard. Le parsing documentaire n'a jamais lieu dans le processus du
moteur : il est exécuté ici, via `run_isolated`/`run_isolated_sync`, sous rlimits (CPU, mémoire,
fichiers ouverts, taille de fichier) avec un timeout — un PDF hostile ou lent ne peut pas
épuiser le processus principal.
"""

from __future__ import annotations

import io
import sys


def extract(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def main() -> int:
    data = sys.stdin.buffer.read()
    if not data:
        sys.stderr.write("pdftool: entrée vide\n")
        return 2
    try:
        text = extract(data)
    except Exception as exc:  # PDF illisible/corrompu : code non nul, pas de traceback
        sys.stderr.write(f"pdftool: extraction échouée: {type(exc).__name__}\n")
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
