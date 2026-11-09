# OSIA — Procédure d'installation

OSIA est un package Python installable (monolithe modulaire, `src/osia`) : CLI `osia`, API REST/SSE et interface web facultative. Aucune image Docker n'est requise (règle AGENTS.md n°8).

## Installation guidée

Dans le dossier du dépôt, lance avec ton compte Linux habituel :

```bash
./install.sh
```

L’assistant demande le mode **Desktop** ou **Server**, une base PostgreSQL locale dédiée ou existante, puis l’activation de l’interface web. Il crée l’environnement Python, installe OSIA, initialise les répertoires et applique les migrations. À la fin, il indique la commande de démarrage propre à ton compte, généralement `~/.local/bin/osia`.

Pour la base locale, PostgreSQL serveur et ses outils doivent être installés. Par exemple, sous Debian ou Ubuntu :

```bash
sudo apt install python3 python3-venv postgresql postgresql-client
```

Sous Fedora, les paquets correspondants sont `python3`, `postgresql-server` et `postgresql`. L’installation des dépendances Python nécessite un accès aux paquets configurés pour `pip`. L’assistant crée une instance PostgreSQL séparée, accessible sur la boucle locale et protégée par un mot de passe généré. Elle démarre pendant l’installation, puis au lancement d’OSIA si nécessaire, et reste active jusqu’à `~/.local/bin/osia db stop`. Son état est consultable avec `~/.local/bin/osia db status`.

Le choix d’une base existante demande son adresse PostgreSQL, saisie sans affichage. Pour une installation non interactive, définis `OSIA_INSTALL_DB_DSN` dans l’environnement puis utilise, par exemple, `./install.sh --mode server --database existing --no-web`. Le mode serveur reste lié à l’adresse locale par défaut et exige une authentification. Son jeton est accessible avec `~/.local/bin/osia auth token` après le premier démarrage.

La configuration est enregistrée dans `~/.config/osia/installation.json` et l’adresse de base, qui peut contenir un mot de passe, dans `~/.config/osia/database.secret`, lisible uniquement par le propriétaire et exclue des sauvegardes. Les variables XDG correspondantes permettent de personnaliser les répertoires. Une installation existante n’est jamais écrasée. Le programme s’exécute au premier plan ; pour l’arrêter, utilise `Ctrl+C`.

La procédure manuelle reste disponible ci-dessous.

## 1. Prérequis

| Élément | Détail |
| --- | --- |
| Système | Linux — Debian 12+, Ubuntu 24.04+, Fedora 40+ testés (CON-01 §1) ; aucune dépendance native compilée côté moteur |
| Python | ≥ 3.11 (3.12 utilisé en CI) |
| PostgreSQL | Une instance accessible (TCP ou socket Unix) et son DSN, transmis par `OSIA_DB_DSN` (ex. `postgresql://osia@127.0.0.1:5432/osia`). Sans `OSIA_DB_DSN`, ce sont les variables standard `PGHOST`/`PGUSER`/… qu'utilise asyncpg |
| Sauvegardes | Binaires `pg_dump`/`psql` de la même version majeure que le serveur PostgreSQL (utilisés par `osia backup`) |
| Non requis | Docker/Podman, Redis, RabbitMQ, Celery, Neo4j (AGENTS.md n°8) |
| Tests (développement) | Extra `test` : `pip install -e ".[test]"` embarque PostgreSQL (`pgserver`), aucune instance externe. Node.js uniquement pour les smoke tests JS du frontend (`tests/js_smoke*.js`) |

## 2. Installation

```bash
python3 -m venv ~/.venvs/osia          # ou : pipx
source ~/.venvs/osia/bin/activate      # ou : pipx install /chemin/vers/OSIA
pip install /chemin/vers/OSIA          # installation depuis le clone du dépôt
osia version                           # vérifie l'installation
```

`python -m osia …` est équivalent à `osia …`.

## 3. Initialisation

```bash
osia init                              # crée l'arborescence (voir §6), répertoires sensibles en 0700
export OSIA_DB_DSN="postgresql://…/osia"
osia db migrate                        # applique les migrations du schéma
```

Les migrations sont aussi appliquées automatiquement au premier démarrage du moteur (`osia serve`, `osia investigation …`).

## 4. Démarrage

**Mode desktop (défaut)** — écoute locale uniquement :

```bash
osia serve                             # API + interface web sur http://127.0.0.1:8471
osia serve --no-web-ui                 # API seule (EXEC-03) — ou OSIA_WEB_UI_ENABLED=0
```

**Mode serveur** — authentification obligatoire (Bearer, T5.7) :

```bash
export OSIA_MODE=server
osia serve                             # le jeton admin est généré au premier démarrage
osia auth token                        # affiche le jeton (fichier 0600) ; osia auth rotate pour le renouveler
# exposition distante : host explicite + HTTPS obligatoire
export OSIA_LISTEN_HOST=0.0.0.0 OSIA_TLS_CERTFILE=… OSIA_TLS_KEYFILE=…
# ou certificat auto-signé local : OSIA_TLS_AUTOGEN=1
```

Port d'écoute : `OSIA_LISTEN_PORT` (défaut 8471). En mode desktop, toute écoute hors loopback est refusée au démarrage.

## 5. Premier pas (CLI)

```bash
osia investigation start --title "…" --hint "…" [--objective "…"] [--profile rapide] [--wait]
osia investigation list
osia events <id>
osia investigation stop <id>
osia investigation export <id> --format both --out ./exports   # archive .osia + rapport HTML
```

## 6. Emplacements (CON-01 §2)

| Rôle | Desktop (XDG) | Serveur (FHS) | Variable d'env. |
| --- | --- | --- | --- |
| Configuration | `~/.config/osia/` | `/etc/osia/` | `OSIA_CONFIG_DIR` |
| Données (base, preuves) | `~/.local/share/osia/` | `/var/lib/osia/` | `OSIA_DATA_DIR` |
| Cache technique | `~/.cache/osia/` | `/var/cache/osia/` | `OSIA_CACHE_DIR` |
| Journaux | `~/.local/state/osia/logs/` | `/var/log/osia/` | `OSIA_LOG_DIR` |
| Sauvegardes | `~/.local/share/osia/backups/` | `/var/backups/osia/` | `OSIA_BACKUP_DIR` |

## 7. Vérification (développement)

```bash
pip install -e ".[test]"
python -m pytest -q                    # hors ligne : PostgreSQL embarqué, connecteurs/IA simulés
```

Référence : run de recette du 07/11/2026 — 256 PASSED, 0 FAILED, aucune désélection (`COWORKAI/RECETTE-APPLICATIVE.md`).

## 8. Sauvegarde, mise à jour, désinstallation

```bash
osia backup create [--dest DIR]        # sauvegarde à chaud (pg_dump + preuves + manifeste)
osia backup list
osia backup verify <id>
osia backup restore <id> --yes        # destructif : confirmation explicite requise
pip install --upgrade /chemin/vers/OSIA
osia version --check                   # notification de version (best-effort, via le NetworkGuard)
pip uninstall osia                     # les données restent dans OSIA_DATA_DIR (suppression manuelle)
```
