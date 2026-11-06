# CON-01 — Installation, emplacements et modes Desktop/Server

**Exigences** : T1 (EXEC-01/02/03), T2.1/T2.3, T3.3, T5.7, V1.1 (installation Linux Desktop et Server, moteur Python + PostgreSQL, CLI et API, web facultatif, accès serveur authentifié).
**Choix d'implémentation** documentés ici, sans rouvrir le produit.

## 1. Distribution et paquetage

- Moteur distribué comme **package Python installable** (`pyproject.toml`, layout `src/osia`), installable par `pip`/`pipx` dans un venv dédié sur toute distribution Linux commune (Debian 12+, Ubuntu 24.04+, Fedora 40+ testés ; aucune dépendance native compilée requise côté moteur).
- Le **frontend web est un extra facultatif** (`pip install "osia[web]"`) ; sans lui, le moteur, la CLI et l'API restent pleinement utilisables (EXEC-03). Aucun Docker/Podman requis (T5.2, CONCEPTION-RESTANTE §1).
- Entrées : `osia` (CLI, `python -m osia`) et `osia-serve` (service moteur + API).

## 2. Emplacements (T2.3, personnalisables)

| Rôle | Desktop (XDG) | Server (FHS, personnalisable) | Variable d'env. de surcharge |
| --- | --- | --- | --- |
| Configuration | `~/.config/osia/` | `/etc/osia/` | `OSIA_CONFIG_DIR` |
| Données persistantes (base, preuves) | `~/.local/share/osia/` | `/var/lib/osia/` | `OSIA_DATA_DIR` |
| Cache technique | `~/.cache/osia/` | `/var/cache/osia/` | `OSIA_CACHE_DIR` |
| Journaux | `~/.local/state/osia/logs/` | `/var/log/osia/` | `OSIA_LOG_DIR` |
| Sauvegardes | `~/.local/share/osia/backups/` | `/var/backups/osia/` | `OSIA_BACKUP_DIR` |

Séparation stricte maintenue entre configuration, données, cache, journaux et sauvegardes (T2.3). Permissions `0700` sur config et data, `0600` sur les fichiers sensibles (T2.7).

## 3. PostgreSQL (T2.1)

- **Desktop** : instance PostgreSQL locale gérée par OSIA (binaire système `postgres`/`initdb` du paquet `postgresql` de la distribution, base dans `OSIA_DATA_DIR/pg`), DSN stocké en config, cycle de vie piloté par `osia db start/stop/status`.
- **Server** : DSN externe configurable (`OSIA_DB_DSN` ou `config.toml`), OSIA ne gère pas le cycle de vie de l'instance.
- En environnement de test/CI : PostgreSQL embarqué user-space (`pgserver`) via `OSIA_DB_DSN` — choix de test uniquement, pas une dépendance produit.

## 4. Modes (EXEC-02)

- `mode = desktop` (défaut) : API liée à `127.0.0.1` uniquement, sans authentification distante requise (liaison locale de confiance), web facultatif.
- `mode = server` : API avec **authentification obligatoire** (jeton de session Bearer, voir CONCEPTION/05 §6), sessions et autorisations (T5.7), exposition distante explicite uniquement (`listen_host`), HTTPS requis pour tout accès distant (terminaison TLS configurable ; en V1, proxy inverse accepté, documenté).
- Le changement de mode migre la configuration et les droits (CON-01 vérification : migration de mode maîtrisée) ; le backend fonctionne **sans aucun frontend** (EXEC-03).

## 5. Vérifications prévues pour ce lot

- `osia init` crée l'arborescence, initialise la base (migrations), démarre en mode desktop sur loopback.
- `osia serve --mode server` refuse de écouter hors loopback sans `listen_host` explicite + auth configurée.
- CLI utilisable sans web : créer/lister/arrêter une investigation par CLI uniquement.
