# CON-02 — Persistance : schéma SQL v1 et protocole de cohérence base/fichiers

**Exigences** : T2.1/T2.2/T2.4, D1, D-INV-03/10, OSIA-I-10, OSIA-I-14, V1.5 (archive `.osia` séparée, non traitée ici).
**Choix d'implémentation** : schéma SQL v1 ci-dessous, protocole d'écriture en 4 phases, déduplication par empreinte.

## 1. Organisation

- PostgreSQL porte toutes les métadonnées et l'état (T2.2) ; les contenus binaires/preuves vivent dans `OSIA_DATA_DIR/proofs/`.
- Migrations : fichiers SQL numérotés `src/osia/store/migrations/NNNN_*.sql`, appliqués dans une transaction par `store.db.migrate()`, table `schema_migrations` (D1.5).
- Connexion : pool `asyncpg` ; DSN en config (CON-01 §3).

## 2. Schéma v1 (tables)

| Table | Rôle clé |
| --- | --- |
| `schema_migrations` | versionnage du schéma |
| `settings` | paramètres hiérarchiques (clé → valeur JSON) |
| `profiles` | profils de recherche (V1.4 : Rapide/Standard/Approfondi) |
| `investigations` | état, limites effectives (instantané, D7.2), clé d'idempotence de lancement |
| `branches` | branches liées, limites propres, profondeur propre |
| `tasks` | file d'ordonnancement durable (T4.2) : état, priorité, profondeur, payload, idempotence |
| `external_ops` | opérations externes (requête source / appel IA) : état, coût estimé, réservation |
| `reservations` | enveloppes budgétaires réservées (clé d'idempotence unique) |
| `ledger` | écritures financières (reserved/consumed/released/reconciled), période `YYYY-MM` |
| `events` | journal structuré (T3.13/T4.9), `id bigserial` = curseur SSE |
| `proof_files` | contenu physique dédupliqué : `sha256` unique, chemin, taille |
| `proof_refs` | provenance par investigation : référence vers `proof_files` + URL source + date de collecte (la dédup ne fusionne pas les provenances, T2.2) |
| `entities`, `relations`, `assertions`, `decisions` | graphe de connaissances (T6) — posées en v1, exploitées par la tranche graphe |

État des enregistrements : colonnes `created_at`/`updated_at` `timestamptz` partout ; suppressions logiques (pas de destruction silencieuse, D-INV-04).

## 3. Protocole de cohérence base/fichiers (T2.4, OSIA-I-10)

Écriture d'une preuve, en 4 phases :

1. Écrire le contenu dans `proofs/incoming/<uuid>.part` (fsync).
2. Calculer SHA-256 ; déplacer atomiquement (`rename`) vers `proofs/sha256/<aa>/<bb>/<sha256>` si absent (dédup physique, T2.2).
3. Dans **une transaction SQL** : insérer `proof_files` (ON CONFLICT DO NOTHING) puis `proof_refs` (investigation, source, date de collecte). Commit.
4. Si la ligne `proof_refs` est présente mais le fichier manque → incohérence détectée au démarrage ; inversement, fichier sans ligne = orphelin.

**Reprise au démarrage** : scan de cohérence — fichiers orphelins supprimés **uniquement s'ils ne sont référencés par aucune preuve conservée** (jamais de suppression de preuve utile, OSIA-I-14) ; lignes sans fichier signalées en erreur et marquées, jamais réécrites silencieusement. Le protocole est testé par injection de crash entre les phases 1–3 (test `test_store_files.py`).

Une transaction SQL seule ne couvre pas le système de fichiers : la phase 2 (fichier) précède la phase 3 (métadonnées) et la reprise ci-dessus referme la fenêtre (T2.4).

## 4. Cache technique (D4)

`OSIA_CACHE_DIR` : réponses de requêtes transitoires, TTL configurable (défaut 24 h min, V1.4). La purge du cache ne touche jamais `proof_files`/`proof_refs` référencés (OSIA-I-14, D4.6.5).

## 5. Vérifications prévues

- Migrations idempotentes, reprise après arrêt brutal (test crash simulé).
- Dédup : deux preuves identiques → un seul fichier, deux `proof_refs` distincts.
- Orphelin base/fichiers détecté et traité sans perte de preuve conservée.
