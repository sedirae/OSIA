# CON-06 — Isolation Linux et contrôle central réseau/destinations

**Exigences** : T5.1 (classification des connecteurs par niveau de confiance, autorisation explicite pour les expérimentaux, connecteurs officiels privilégiés en V1), T5.2 (isolation par processus + limites CPU/mémoire/fichiers ; un sous-processus seul n'est pas une sandbox contre du code hostile ; Docker/Podman non obligatoires), T5.4 (politique réseau centralisée indépendante des connecteurs : domaines autorisés/interdits, anti-SSRF, contrôle des redirections/délais/tailles/fréquences), T5.5 (secrets non persistés en clair, coffre chiffré facultatif, jamais dans journaux/exports/prompts), T5.6 (contenus externes = données non fiables, jamais des ordres), T5.9 (blocages journalisés dans l'audit de sécurité). Vérification attendue (CONCEPTION-RESTANTE) : *restrictions fichiers/réseau, redirections et contenus adverses*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. V1 reste sans conteneur obligatoire (T5.2) : les rlimits bornent les sous-processus, ils ne remplacent pas une sandbox pour du code hostile.

## 1. Politique réseau centralisée — `netguard.NetworkGuard` (T5.4)

- Toute requête sortante des connecteurs passe par le guard : schéma **http/https uniquement**, domaine dans la denylist ou hors allowlist → refus (`NetworkDeny`).
- **Anti-SSRF** : résolution DNS puis filtrage de **chaque IP résolue** contre les réseaux bloqués par défaut (loopback, RFC1918, CGNAT 100.64/10, link-local 169.254/16 incl. metadata cloud, multicast, ULA fc00::/7, ::1…). Les IP littérales sont filtrées directement. Toute IP bloquée → refus `ssrf_ip_bloquee`.
- **Redirections** suivies manuellement (max 3), **re-vérifiées à chaque saut** (check URL + résolution) — une redirection vers l'interne est bloquée.
- Limites : timeout 15 s (V1.4), taille de réponse plafonnée (`OSIA_NET_MAX_BYTES`, défaut 10 Mo), rate limit par domaine (1 req/s).
- Allowlist effective = `OSIA_NET_ALLOW_DOMAINS` + domaines déclarés des connecteurs enregistrés ; denylist = `OSIA_NET_DENY_DOMAINS`.
- **Blocages journalisés** dans l'audit de sécurité (`net.blocked`, T5.9) avec host + raison, **sans l'URL complète** (les query strings peuvent contenir des secrets).
- API : `GET /api/v1/net/policy` ; CLI : `osia net policy`.

## 2. Niveaux de confiance des connecteurs (T5.1)

- `TrustLevel` (official/approved/experimental) dans le manifeste ; les connecteurs **EXPERIMENTAL sont désactivés par défaut** au registre.
- Un connecteur expérimental exige une **autorisation explicite persistée** (setting `allow_experimental:<id>`) : refus `experimental_sans_autorisation_explicite` sinon (vérifié dans le handler de source).
- API : `GET /api/v1/connectors`, `POST /api/v1/connectors/{id}/toggle` (`confirm: true` exigé pour un experimental) ; CLI : `osia connectors list|toggle --confirm`. Changements audités (`op.connector.toggle`).

## 3. Coffre de secrets — `security.SecretStore` (T5.5)

- Secrets en **mémoire** ; persistance facultative **chiffrée AES-256-GCM** (`config_dir/secrets.enc`, clé locale aléatoire dans `config_dir/secrets.key` 0600, ou passphrase `OSIA_SECRETS_PASSPHRASE` via Argon2id — même profil que CON-15).
- Fichiers écrits en 0600 dès la création (`secure_write`) ; la valeur n'apparaît **jamais en clair** sur disque, dans les logs, les exports ou les prompts. API : `GET /api/v1/secrets` (noms seuls), `PUT/DELETE /api/v1/secrets/{name}` (audité sans la valeur) ; CLI : `osia secrets list|set|get|delete` (valeur via env ou prompt, jamais en argument).

## 4. Isolation par processus — `security.run_isolated` (T5.2)

- Sous-processus avec **rlimits** appliqués avant exec (RLIMIT_CPU, RLIMIT_AS 512 Mo, RLIMIT_NOFILE 64, RLIMIT_FSIZE 100 Mo) + timeout avec kill. Variante async (`run_isolated`) et synchrone (CLI).
- Conformément à T5.2, ce n'est **pas** une sandbox contre du code hostile : c'est une barrière de limites pour les traitements sensibles (extraction documentaire, outils externes). Le renforcement conteneur reste possible pour les connecteurs non fiables, sans être un prérequis V1.

## 5. Contenus adverses et provenance (T5.6)

- `store_proof` valide l'URL de provenance : schéma **http/https uniquement** (refus sinon) — une source collectée ne peut pas injecter un schéma dangereux (file:, gopher:…).
- Les contenus collectés restent des **données** : stockés (dédup SHA-256), jamais exécutés ; le rapport HTML échappe tout contenu externe (vérifié par les tests de rapport) ; le web n'utilise jamais `innerHTML` (PR #7).

## 6. Vérifications réellement exécutées

- `pytest -q` : **99 tests passés** (dont 15 dans `tests/test_con06.py`, y compris les correctifs d'audit : IP littérale publique soumise à l'allowlist, port invalide refusé, sel Argon2id aléatoire par coffre, coffre illisible jamais écrasé), pgserver embarqué.
- Couvert : check_url (schémas, allowlist/denylist, IP littérales internes bloquées incl. 169.254.169.254 et ::1) ; anti-SSRF par résolution DNS (resolver injecté) ; redirection vers l'interne bloquée ; redirection OK suivie ; taille plafonnée ; trop de redirections ; SecretStore mémoire + persistance chiffrée (0600, valeur absente du disque, rechargement) ; `run_isolated` OK et process tué au dépassement CPU ; connecteur experimental désactivé par défaut ; API net/secrets/connectors (toggle experimental sans confirm → 400) ; audit sans secrets ; `store_proof` rejette `file://`.

## 7. Limites

- Le rate limit est en mémoire par processus (redémarrage = remise à zéro) — suffisant en V1 mono-processus.
- La résolution DNS peut varier (DNS rebinding) : le filtrage s'applique à chaque requête via `resolve_and_check`, sans épinglage d'IP (V1, mono-processus local).
- Playwright isolé (T5.3) n'est pas encore branché : le connecteur « Web par URL » V1.2 fait d'abord du HTTP simple via ce guard ; Playwright viendra avec CON-07/CON-08 si nécessaire et autorisé.
