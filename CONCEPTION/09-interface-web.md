# CON-17 + complément client de CON-12 — Interface web (lot C), maquettes, charte et accessibilité

**Exigences** : lot C (C1–C7, règles C1-01…C7-20, REC-C-01…REC-C-19), V1.1 (interface web facultative, investigation/vérification/restitution consultables), V1.6 (charte visuelle, WCAG 2.2 AA visé), T6.9/T7.5 (performances graphe et consultation hors ligne), D5 (restitution), T5.7/EXEC-05 (sécurité des modes même sans frontend), T3.7/T4.9/V1.5 (contrats, SSE, curseur), CON-17 et complément CON-12 côté client.
**Choix d'implémentation** : frontend **statique vanilla** (HTML + CSS + JS sans framework ni étape de build), embarqué dans le package (`src/osia/web/`) et servi par le serveur FastAPI existant. Ce document ne rouvre aucun arbitrage ; il précise CON-17 et les modalités d'implémentation des règles C1–C7.

## 1. Architecture et portée (C1, EXEC-03, CON-01)

- Le moteur reste indépendant des interfaces (T3) : CLI et API `/api/v1` restent pleinement utilisables **sans** le frontend (EXEC-03). Le frontend est un client de l'API ; il ne contient aucune règle métier.
- Choix d'implémentation : fichiers statiques servis sur `/` (`index.html`) et `/static/*` par `create_app` (FastAPI), embarqués via `package-data` (`osia.web`). Aucun framework JS, aucun bundler, aucune dépendance externe : un seul `app.js` en ES2020 vanilla. Ce choix est un détail d'implémentation, pas une décision produit (lot C §1.1).
- En mode `server`, **toutes** les routes y compris `/` et `/static/*` exigent le jeton Bearer (T5.7, EXEC-05) : la protection ne dépend pas de la présence d'un frontend.
- Le jeton saisi dans l'interface est conservé en `sessionStorage` uniquement (jamais en `localStorage` persistant, jamais journalisé, OSIA-I-12) et envoyé en en-tête `Authorization: Bearer …`.

## 2. Organisation de la page (C1, V1.6)

- **Une seule page** (C1-01) : en-tête avec saisie (objectif facultatif + indices + paramètres avancés repliables en `<details>`, C2-03), puis l'espace d'investigation.
- Grand écran (V1.6) : graphe au **centre**, suivi (état, journal, consommation) en colonne gauche, **panneau latéral droit** pour les fiches/preuves ouvertes à la demande (C1-02). Petit écran : les vues s'empilent (media query ≤ 900 px, C1-05, REC-C-02).
- Panneaux **fermables** ; fermer un panneau ne perd ni la sélection ni la position du graphe (état conservé en mémoire, C1-03, C1-04, REC-C-01). Bouton « vue d'ensemble » pour y revenir (C1-06).
- Charte V1.6 : fond `#F5F7FA`, surfaces blanches, texte ardoise `#172033`, accent bleu `#2458C6` ; thème clair uniquement (thème sombre = V2). Liens confirmés = trait plein, hypothèses = pointillés, contradictions = marquage distinct (C4-15, V1.6).

## 3. Saisie et suivi (C2)

- Saisie directe : titre, **objectif facultatif** en langage naturel (C2-01), **plusieurs indices** (C2-02), paramètres avancés repliables : profil (V1.4), surcharges de limites, sources (C2-03/C2-04). Lancement avec `Idempotency-Key` (V1.5) ; une configuration non admissible est refusée avec le motif (C2-05, `403 policy_denied`).
- Suivi : badge d'état distinguant **non lancée / en cours / terminée (objectif étayé) / arrêtée sur limite / arrêtée par l'utilisateur / en erreur** avec la cause (`stop_reason`, C2-12, REC-C-05) ; journal des événements en direct via SSE (C2-07) ; compteurs réels entités/relations/découvertes et profondeur (C2-06).
- Consommation affichée depuis `GET …/budget` : **réservé / consommé / disponible** et plafonds, jamais confondus (C2-09) ; **aucun pourcentage de progression** (C2-10, REC-C-04).
- Actions : arrêter (C2-11), reprendre après incident, sauvegarde manuelle (lien vers la section sauvegardes).

## 4. Synthèse (C3)

- Panneau « Synthèse » listant les assertions de l'investigation, les **décisives d'abord**, avec pour chacune : la qualification d'étayage textuelle parmi **documenté / corroboré / à confirmer / contradictoire / non établi** (C3 tableau, C3-08 — jamais de score chiffré, C3-07), la nature (fait/hypothèse/indice/…), et un badge **séparé** de décision humaine (C6, invariant 4).
- Chaque conclusion substantielle renvoie vers ses entités/relations/sources (C3-03, REC-C-06) : liens cliquables ouvrant les fiches ; une hypothèse non démontrée est identifiée comme telle (C3-09).
- Statut **provisoire** pendant l'exécution (C3-04) ; à l'arrêt, le rapport stabilisé reste consultable dans l'interface (C7-16, REC-C-17). Une correction ultérieure signale la synthèse comme **à actualiser** plutôt que de l'écraser (C3-06, A11) : badge affiché tant qu'aucune nouvelle évaluation d'objectif n'a été émise.

## 5. Graphe (C4, T6.9, CON-17 performances)

- Rendu **SVG vanilla** (pas de bibliothèque externe). Trois modes (C4-08/09/10) : **réseau** (layout à ressorts simplifié, itérations bornées), **arborescent** (BFS depuis les racines — chemins d'exploration, jamais présentés comme une hiérarchie réelle, C4-09), **regroupé** (par catégorie d'entité, groupes repliables avec compteur d'éléments masqués, C4-10/C4-11).
- Interactions : zoom (molette), déplacement (glisser), **fixation manuelle des nœuds** (position conservée en session, C4-07), sélection nœud → fiche entité (C4-02), sélection arête → type/statut/sources (C4-03), recherche/mise en évidence d'une entité (C4-05), filtres par type/statut/profondeur (C4-06), exploration progressive (C4-04).
- Sémantique visuelle (C4-14…C4-17, V1.6) : couleur/forme par catégorie d'entité ; **trait plein = documenté/corroboré, pointillés = à confirmer/non établi, rouge + libellé = contradictoire** ; les relations rejetées sont masquables mais restent consultables (C4-16).
- Masqué ≠ absent (C4-13, REC-C-08) : compteur « N masqués par les filtres / M au total » ; les filtres sont purement visuels (C4-12).
- Performance (C4, CON-17) : rendu par lots via `requestAnimationFrame`, plafond d'affichage côté serveur 500 entités (API) avec regroupement proposé au-delà ; aucun seuil fixe imposé.

## 6. Fiches contextuelles (C5)

- Panneau latéral : aperçu immédiat, sections dépliables (détails, provenance **par attribut**, relations entrantes/sortantes, branches concernées, historique des décisions) (C5, REC-C-10).
- Trois couches explicitement distinctes (C3.2) : données de sources / interprétations IA / interventions humaines, avec la provenance (source, URL, date) au niveau de chaque information.

## 7. Validation et correction (C6)

- Sur chaque fiche (entité/relation/assertion/proposition de rapprochement) : **valider, rejeter, corriger, annoter** et **annuler** une décision (`reverts`), via `POST …/decisions` ; chaque action est historisée avec cible, version, date et justification facultative (C6-11/C6-12) et l'historique reste consultable (C6-14, REC-C-13).
- L'étayage documentaire et la décision humaine restent deux statuts indépendants (invariant 4, REC-C-12) ; une correction met à jour les vues et signale les synthèses à réanalyser (C6-15, REC-C-14) ; aucune réanalyse payante hors budget sans nouvel accord (C6-18, REC-C-19).

## 8. Branches, vues consolidées et restitution (C7)

- **Arbre des investigations** affiché séparément du graphe relationnel (C7, invariant 3) : chaque branche avec objectif, contexte, état, journal et consommation propres (C7-02/C7-08) ; navigation sans perdre le graphe (C7-01).
- Vues **par branche** (filtre `branch_id`) et **consolidée** (toutes branches) (C7-09, REC-C-16) ; les contradictions entre branches restent visibles (C7-12).
- Pistes d'approfondissement **suggérées mais jamais lancées seules** (C7-04/C7-05, REC-C-15) : le lancement d'une branche exige une **acceptation explicite de ses limites** (C7-06) → `POST …/branches` avec `explicit_acceptance: true` (sinon `403`).
- Restitution : le **rapport est consultable dans l'interface avant tout export** (C7-16, REC-C-17) via le panneau Synthèse/dossier (assertions, qualifications, décisions, preuves) ; le rapport HTML autonome reste un **export manuel** ouvrable hors ligne (T7.5). Exports portables **manuels uniquement** (C7-18) : `.osia` / HTML / les deux, périmètre branche ou consolidé affiché (C7-17), exclusions cochées, chiffrement facultatif (la phrase n'est jamais journalisée, OSIA-I-12). Import : prévisualisation puis application supervisées, par upload binaire `application/octet-stream` accepté sur `POST /api/v1/import/apply` (évolution compatible v1 ; `mode`/`on_conflict`/`passphrase` en query params). Sauvegardes manuelles : créer/lister/vérifier.

## 9. Temps réel, resynchronisation et sécurité (T4.9, V1.5, T5.7, T5.6)

- SSE consommé via `fetch` + lecture du flux (permet l'en-tête `Authorization`) avec **curseur `last_event_id`** et relecture de l'état après déconnexion (V1.5, CON-12) : aucune tâche relancée en double côté client.
- CSP : `default-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'self'` ; aucun script inline. **Tout contenu collecté est échappé** (rendu par `createElement`/`textContent`, jamais `innerHTML` avec des données externes, T5.6/OSIA-I-01).
- Mode serveur : écran de saisie du jeton en cas de `401` ; les routes statiques sont protégées comme l'API (EXEC-05).

## 10. Accessibilité (V1.6, CON-17)

- Niveau visé **WCAG 2.2 AA** : navigation clavier complète (ordre logique, `:focus-visible` visible, Échap ferme un panneau, nœuds du graphe focusables), rôles ARIA (`main`, `complementary`, `dialog` pour les panneaux, `aria-live="polite"` sur le journal), contraste vérifié sur les couleurs de la charte (ardoise `#172033` et accent `#2458C6` sur fond `#F5F7FA`/blanc).
- Aucune conformité annoncée sans vérification : recette manuelle + contrôles automatisés limités (présence des attributs, parcours clavier) ; audit complet reporté (CON-19).

## 11. Vérifications prévues (exécutées dans la PR)

- Tests pytest : `/` et `/static/*` servis avec les bons types MIME, traversal de chemin refusé, mode serveur → `401` sans jeton sur `/` **et** `/static/*`, API inchangée ; smoke Node de `app.js` (chargement sans exception avec DOM simulé, rendu de la vue d'accueil).
- Recette manuelle tracée (REC-C-01…19) : non exécutée en CI ; la PR liste les scénarios couverts par tests et ceux restant en recette manuelle.
