# CON-14 / CON-15 / CON-16 + restitution HTML — archives `.osia`, rapport autonome, sauvegarde à chaud

**Exigences** : D5 (option C enrichie), T7.1–T7.9, T2.5/T2.6, T2.8, V1.1 (Restitution, Sauvegarde technique), V1.5 (`format_version: "1.0"`, chiffrement facultatif du manifeste inclus), V1.6 (charte), REC-D5-01…05, AC-T7-01…09, AC-T2-06, OSIA-I-12 (aucun secret dans les exports), OSIA-I-14 (jamais de perte de preuve).
**Choix d'implémentation** : conteneur ZIP (ZIP64 automatique), JSON/JSONL, SHA-256, chiffrement facultatif AES-256-GCM + Argon2id, rapport HTML unique autonome, sauvegarde manuelle `pg_dump` + copie cohérente des preuves. Ce document ne rouvre aucun arbitrage ; il précise CON-14/CON-15/CON-16 et la restitution HTML de T7.5/D5.7.1B.

## 1. CON-14 — Spécification de l'archive `.osia` (T7.1, T7.2, T7.4, T7.6, T7.7, V1.5)

### 1.1 Conteneur

- Archive = fichier ZIP (ZIP64 automatique au-delà de 4 Go, `zipfile` Python). Indépendante de l'installation d'origine (T7.1).
- Deux états :
  - **non chiffré** : `manifest.json` en clair + `data/*.jsonl` + `proofs/<sha256>` ;
  - **chiffré** : `meta.json` en clair (format, version, `encrypted: true`, paramètres KDF) + `manifest.json.enc` + `enc/<n>.enc` (noms opaques : index séquentiel, le manifeste chiffré porte le chemin interne en clair — les métadonnées sensibles, dont les noms internes, ne restent pas exposés, T7.3/V1.5).

### 1.2 Manifeste `manifest.json` (`format_version: "1.0"`, V1.5)

```json
{
  "format": "osia-archive",
  "format_version": "1.0",
  "created_at": "…", "osia_version": "0.1.0", "encrypted": false,
  "scope": {
    "investigation_ids": ["inv_…"],
    "branch_ids": null,
    "include_proofs": true,
    "exclusions": ["tasks", "events"],
    "partial": false
  },
  "counts": {"branches": 2, "entities": 12, "relations": 9, "assertions": 20, "proof_refs": 7, "proof_files": 5, "decisions": 3},
  "warnings": ["assertion ass_… référence la preuve exclue proof_…"],
  "files": [{"path": "data/entities.jsonl", "sha256": "…", "size_bytes": 1234}]
}
```

- `files` liste **chaque** fichier de l'archive avec empreinte SHA-256 et taille (T7.2) ; vérification systématique avant toute lecture/utilisation (import, preview, vérification).
- `scope.partial: true` dès qu'une exclusion ou une sélection de branches rend l'export incomplet : une exportation partielle n'est jamais présentée comme complète (T7.4). Les avertissements listent les assertions/relations dont les `proof_ids` référencent des preuves exclues (chaîne de preuve rompue, T7.4).
- Exclusions possibles (T7.4) : `proofs` (métadonnées `proof_refs` conservées, binaires absents), et au choix `tasks`, `external_ops`, `reservations`, `ledger`, `events` (données techniques/financières). Jamais de secrets : clés API, jetons, `auth_token_hash` et toute colonne `settings` contenant `token`/`secret`/`key`/`password` sont **systématiquement exclus** (D5.7.1A, OSIA-I-12) — test de filtrage obligatoire.

### 1.3 Contenu (tables exportées, JSONL, une ligne = un enregistrement complet)

`investigation.json` (1 ligne), `branches`, `tasks`, `external_ops`, `reservations`, `ledger`, `events`, `entities`, `entity_identifiers`, `relations`, `assertions`, `match_proposals`, `decisions`, `proof_refs` (toutes en JSONL sauf investigation), `proofs/<sha256>` (binaires originaux si `include_proofs`).

- Identifiants, dates, graphes, décisions humaines et historique sont conservés tels quels (D5.7.1A intangible).
- Sélection : par investigation, éventuellement restreinte à des `branch_ids` (T7.4) ; les entités/relations/assertions non rattachées aux branches retenues sont exportées si elles appartiennent à l'investigation (le graphe est propre à l'investigation, T6).

### 1.4 Import supervisé et non destructif (T7.6, D5.7.2)

1. **Vérification** : type de fichier, `format`/`format_version` (refus propre avec diagnostic si version inconnue, T7.7), intégrité SHA-256 de chaque fichier (rapport des erreurs, T7.2), déchiffrement si `encrypted` (échec contrôlé au déverrouillage, CON-15).
2. **Prévisualisation** : inventaire (counts), périmètre, exclusions, avertissements, **détection des conflits** (investigation/élément déjà présent avec un contenu différent, collisions d'`idempotency_key`) — aucune modification locale à ce stade.
3. **Choix d'import** : mode `add` (nouveau dossier : les identifiants en collision sont re-mappés avec un nouveau préfixe et la correspondance est consignée dans le rapport d'import) ou mode `merge` (les éléments strictement identiques sont ignorés, les divergences restent des conflits explicites soumis à `on_conflict: fail` (défaut) ou `skip` ; **aucun écrasement silencieux**, D5.7.5). La restauration complète destructrice n'est pas exposée en API en V1 : CLI uniquement, avec confirmation explicite et sauvegarde préalable automatique (D5.7.2).
4. **Application transactionnelle** : une seule transaction PostgreSQL pour toutes les insertions ; en cas d'erreur, rollback complet. Les fichiers de preuves sont d'abord écrits dans `incoming` puis déplacés selon le protocole CON-02 §3.
5. **Aucune reprise de recherche** : une investigation importée dans l'état `running` est ramenée à `suspended` (événement `import.state_normalized`) ; aucun appel IA ni tâche n'est lancé par l'import (D5.7.2 intangible, REC-D5-01).

### 1.5 Journal des exports (T7.8)

Table `exports` (migration `0004`) : `id`, `created_at`, `format` (`osia`|`html`|`both`), `investigation_ids`, `branch_ids`, `exclusions`, `encrypted`, `manifest_sha256`, `counts`, `warnings`. Aucun secret (OSIA-I-12).

## 2. CON-15 — Profil cryptographique facultatif (T7.3, T7.2, D2/D6)

- Chiffrement **authentifié** AES-256-GCM (`cryptography`), clé 32 octets dérivée de la phrase secrète par **Argon2id** (`argon2-cffi`) : `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, sel aléatoire 16 octets par archive.
- Chaque fichier chiffré individuellement : nonce aléatoire 12 octets, stocké dans le manifeste chiffré à côté du chemin interne et du SHA-256 du contenu **en clair** (double contrôle : tag GCM + empreinte T7.2 après déchiffrement).
- La phrase secrète n'est **jamais** stockée dans l'archive (T7.3) ; seul le sel et les paramètres KDF sont en clair (`meta.json`).
- L'archive chiffrée protège aussi le manifeste (V1.5) : `meta.json` clair ne contient aucun nom de fichier interne.
- Consultation/restauration **hors ligne** (T7.3) : le déchiffrement est local, sans réseau.
- Signature d'auteur : **non requise** (T7.2/D5.7.4 : distincte de l'intégrité, facultative, hors V1).
- Dépendances ajoutées : `cryptography>=43`, `argon2-cffi>=23` (découlent de ce choix de conception, PROJECT-INIT).

## 3. Restitution HTML autonome (T7.5, D5.7.1B, V1.6, REC-D5-03/04)

- **Un fichier `.html` unique**, consultable hors ligne sans OSIA ni serveur : toutes les données embarquées dans un `<script type="application/json" id="osia-data">` (séquence `</` échappée en `<\/`), rendu par un **script embarqué unique et maîtrisé** (vanilla JS, aucun chargement externe, aucun CDN).
- **Aucun appel réseau** à l'ouverture : pas de `fetch`/`XMLHttpRequest`/`WebSocket`/préchargement ; les URLs de sources sont affichées comme texte (ouverture volontaire uniquement). **Aucun contenu actif provenant des sources collectées n'est exécuté** (T7.5) : les binaires de preuves ne sont pas inlinés dans le HTML ; seules les métadonnées (hash, URL, date, type) et les textes d'assertions/entités, échappés HTML, y figurent.
- Vues (T7.5) : synthèse (titre, objectif, état, étayage de l'objectif), graphe SVG zoomable (liens pleins = `confirmed`, pointillés = `hypothesis`, libellé visible = `contradicted`, V1.6), arbre des investigations/branches, fiches entités/relations/assertions, chronologie (events), contradictions, décisions humaines, sources/preuves. Recherche et filtres texte. Navigation clavier, focus visible, contraste WCAG 2.2 AA (V1.6) : charte claire — fond `#F5F7FA`, surfaces blanches, texte `#172033`, accent `#2458C6`.
- **Exclusions effectives** (D5.7.1B, REC-D5-04) : une donnée exclue n'est pas présente dans le fichier produit (ni cachée visuellement) ; test automatisé de recherche de la valeur exclue dans le HTML.
- Bannière explicite : un HTML non chiffré est **lisible par toute personne possédant le fichier** (D5.7.1B). Le rapport est une photographie en lecture seule, distinct de l'archive de restauration (T7.9).
- Export combiné `both` (D5.7.1C) : `.osia` + `.html` en une opération.

## 4. CON-16 — Sauvegarde technique manuelle à chaud (T2.5/T2.6, V1.1, AC-T2-06)

- **Manuelle en V1** (programmation reportée V1.1), destination configurable (`OSIA_BACKUP_DIR` par défaut, T2.3).
- Protocole « à chaud » sans arrêt du moteur (T2.6) :
  1. `pg_dump` de la base (snapshot cohérent interne PostgreSQL ; format `custom` si le binaire est disponible, sinon SQL plain) ;
  2. copie du répertoire `proofs/sha256/` (les preuves écrites pendant la sauvegarde suivent CON-02 §3 : fichier posé avant la ligne SQL, donc un éventuel orphelin est nettoyé par le scan de cohérence au démarrage, jamais une preuve référencée n'est perdue, OSIA-I-14) ;
  3. `manifest.json` de la sauvegarde : horodatage, version du schéma (`schema_migrations`), empreintes SHA-256 du dump et de chaque fichier copié, compteurs ;
  4. entrée dans la table `backups` (journal, sans secrets).
- **Vérification** : re-hash de tous les fichiers + `pg_restore --list` (custom) avant toute utilisation ; rapport des erreurs d'intégrité (T7.2/T2.6).
- **Restauration** (T2.6, D5.7.2) : CLI uniquement, confirmation explicite `--yes` ; si la base cible est non vide, une sauvegarde préalable de l'état courant est automatiquement créée ; restauration = recréation de la base depuis le dump + remplacement du répertoire de preuves, puis scan de cohérence CON-02 au démarrage. Test de restauration sur installation de test (AC-T2-06).
- Une archive `.osia` ne remplace pas cette sauvegarde (T7.9) ; la sauvegarde ne remplace pas l'archive portable.
- Espace disque (T2.8) : `GET /api/v1/backups` expose taille et rétention manuelle (suppression explicite uniquement, jamais automatique de preuves conservées).

## 5. Interfaces (CON-12, V1.5)

- API `/api/v1` : `POST /investigations/{id}/export` (`format`, `branch_ids`, `include_proofs`, `exclusions`, `encrypt`) → `201` + manifeste + `export_id` ; `GET /exports`, `GET /exports/{id}`, `GET /exports/{id}/download?file=` ; `POST /import/preview` (fichier uploadé ou chemin serveur), `POST /import` (`mode`, `password`, `on_conflict`) ; `POST /backups`, `GET /backups`, `GET /backups/{id}`, `POST /backups/{id}/verify`. **Pas d'endpoint de restauration destructive en V1** (CLI uniquement). Erreurs JSON stables (`integrity_error`, `unsupported_version`, `import_conflict`, …).
- CLI : `osia investigation export <id> --format osia|html|both --out … [--branch …] [--no-proofs] [--exclude …] [--encrypt]` ; `osia import <fichier> [--preview] [--mode add|merge] [--on-conflict fail|skip] [--yes]` ; `osia backup create|list|verify|restore`.
- L'ouverture d'un rapport ou d'une archive n'exécute aucune recherche (AGENTS.md règle 9).

## 6. Vérifications prévues (exécutées réellement, citées dans la PR)

- Round-trip `export → import` sur base de test : branches, graphe, sources, décisions restitués sans aucun appel IA (REC-D5-01) ; conflit détecté sans écrasement (REC-D5-02) ; HTML hors ligne sans appel externe (scan du fichier : aucune URL externe embarquée, REC-D5-03) ; donnée exclue absente du HTML (REC-D5-04) ; archive chiffrée requiert la phrase, archive corrompue refusée avec diagnostic (REC-D5-05).
- Sauvegarde à chaud + vérification + restauration sur installation de test (AC-T2-06).
- Aucun secret dans exports/journaux (test de filtrage OSIA-I-12).
- `pytest` complet green sur PostgreSQL embarqué (`pgserver`).
