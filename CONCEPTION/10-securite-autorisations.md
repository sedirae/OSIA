# CON-05 — Autorisations, identité/session serveur, TLS et sécurité locale

**Exigences** : T5.7 (sécurité de l'interface et de l'API selon le mode : desktop = liaison locale par défaut, serveur = authentification obligatoire, sessions et autorisations contrôlées, HTTPS pour accès distants, audit des accès sensibles ; protections effectives même sans frontend), T5.9 (journal d'audit de sécurité distinct, protégé, rétention limitée et configurable, pas de secrets), T1 (liaison locale par défaut, accès distant activé explicitement), D6 (confidentialité native, local-first, sécurité graduée), V1.1 (accès serveur authentifié selon T5.7). Vérification attendue (CONCEPTION-RESTANTE) : *refus d'accès non autorisé même sans frontend*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. V1 est mono-utilisateur local-first (A/D, D6) : il n'y a pas de gestion collaborative de comptes à inventer ; le rôle unique est **admin** (propriétaire de l'hôte). Le « contrôle des autorisations » se traduit par : authentification obligatoire en mode serveur, sessions expirables/révocables, audit de sécurité des accès et opérations sensibles, et garde-fous de démarrage (pas d'exposition distante implicite ni non chiffrée).

## 1. Modes et garde-fous de démarrage (T1, T5.7)

- `Settings.validate_runtime()` est appelé avant tout démarrage (`run_server`) :
  - **mode desktop** : `listen_host` doit être local (`127.0.0.1`, `localhost`, `::1`) — sinon `ConfigError` (aucune exposition distante implicite) ;
  - **mode serveur** exposé (host non local) : HTTPS obligatoire — certificats fournis (`OSIA_TLS_CERTFILE`/`OSIA_TLS_KEYFILE`) ou autogénérés (`OSIA_TLS_AUTOGEN=1`), sinon `ConfigError`.
- En mode serveur sur écoute locale, TLS reste facultatif (certificats fournis = TLS activé quel que soit le host).

## 2. Identité et sessions serveur (T5.7)

- **Jeton administrateur statique** (rétrocompatible) : `OSIA_AUTH_TOKEN` ou hash stocké en setting `auth_token_hash` ; comparaison en temps constant (`hmac.compare_digest` sur SHA-256).
- Si aucun jeton n'est configuré en mode serveur, `ensure_server_credentials` en génère un au démarrage : hash SHA-256 en base, jeton en clair écrit une seule fois dans `config_dir/auth_token` (0600), événement `auth.token.issued` audité **sans le secret**. Commandes CLI : `osia auth token` (affiche le jeton local), `osia auth rotate` (nouveau jeton + révocation de toutes les sessions + audit).
- **Sessions** : `POST /api/v1/auth/login` (mode serveur uniquement) échange le jeton admin contre un jeton de session opaque `sess_…` (32 octets aléatoires), stocké **hashé** en table `sessions` (migration 0005), avec expiration (`OSIA_SESSION_TTL_HOURS`, défaut 8 h) et révocation (`POST /api/v1/auth/logout`, `osia auth rotate`). `GET /api/v1/auth/sessions` liste les sessions actives sans jamais exposer de hash.
- `require_auth` accepte le jeton statique **ou** une session valide ; s'applique à **toutes** les routes API, `/` et `/static/*` (même sans frontend, EXEC-05). En mode desktop, aucune authentification distante n'est requise (liaison locale).

## 3. Autorisations (T5.7, D6)

- V1 mono-utilisateur : tout client authentifié en mode serveur a le rôle **admin** ; aucune gestion multi-utilisateur n'est introduite (A §20, C6-13). Les opérations sensibles (export, téléchargement d'export, import apply, sauvegarde create/verify) sont **auditées** individuellement (T5.9) via `_audit_op`.

## 4. TLS pour accès distants (T5.7, T1)

- Certificats fournis via `OSIA_TLS_CERTFILE`/`OSIA_TLS_KEYFILE` → uvicorn en HTTPS.
- `OSIA_TLS_AUTOGEN=1` + host non local → certificat **auto-signé local** généré avec `cryptography` (RSA 2048, SAN `osia.local` + 127.0.0.1, 365 j) dans `config_dir/tls/`, répertoire 0700, clé/cert 0600 (`ensure_self_signed_cert`). Aucun secret transmis au réseau.

## 5. Journal d'audit de sécurité (T5.9)

- `SecurityAudit` : fichier JSONL **distinct** de la télémétrie technique (`log_dir/security-audit.jsonl`), créé en **0600**, rétention configurable (`OSIA_AUDIT_RETENTION_DAYS`, défaut 90 j, purge à l'écriture).
- Événements : `auth.login` (succès/échec), `auth.logout`, `auth.denied` (avec IP client), `auth.token.issued`, `auth.token.rotated`, `op.export`, `op.export.download`, `op.import.apply`, `op.backup.create`, `op.backup.verify`.
- **Aucun secret journalisé** : les clés sensibles (`token`, `authorization`, `passphrase`, `secret`, `password`, `key`, `session_token`, `api_key`) sont masquées (`***`) par `_scrub` ; les valeurs texte tronquées à 256 caractères.
- CLI : `osia audit [--limit N]` affiche le journal.

## 6. Sécurité locale (D6)

- `Paths.ensure()` : répertoires sensibles en **0700** (config, data, logs, backups, proofs) ; `secure_write()` crée les fichiers sensibles (jeton, clés TLS) en **0600** dès la création.
- Correction de `Repo.get_setting` : la colonne jsonb `settings.value` est lue en texte brut par asyncpg ; les scalaires JSON sont désormais décodés (sinon un hash stocké revenait avec des guillemets et ne correspondait jamais).

## 7. Vérifications réellement exécutées

- `pytest -q` : **84 tests passés** (dont 9 nouveaux dans `tests/test_security.py`) avec PostgreSQL embarqué `pgserver`.
- Couvert par les tests : 401 sur toutes les routes (API + `/` + `/static/*`) sans credential en mode serveur ; login succès/échec ; session valide/expirée/révoquée ; jeton statique accepté ; `login` refusé en mode desktop (400) ; `validate_runtime` bloque desktop non local et serveur exposé sans TLS ; journal d'audit en 0600 sans secrets ; répertoires 0700 ; certificat auto-signé avec clé 0600 ; génération unique du jeton serveur (hash en base, fichier 0600, audit sans secret).

## 8. Limites

- Certificat auto-signé : adapté à un accès local/LAN de confiance, pas à une exposition Internet publique (pas de CA reconnue) — conforme à T5.7 (HTTPS obligatoire), la confiance du certificat reste du ressort de l'administrateur.
- Rétention de l'audit par purge périodique à l'écriture (pas de tâche planifiée) — la programmation des sauvegardes/tâches est reportée (V1.1).
- Pas de verrouillage de compte après N échecs (mono-utilisateur local, surface d'attaque bornée par le réseau) — à réévaluer si un mode multi-utilisateur voyait le jour (hors V1).
