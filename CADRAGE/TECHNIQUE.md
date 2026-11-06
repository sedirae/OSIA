# OSIA — Conception technique transversale

**Version :** v0.1 — 05/11/2026  
**Statut global :** PROPOSÉ — conception transversale non validée intégralement ; **lot T1 validé** le 06/11/2026 (voir [T1-EXECUTION-DISTRIBUTION.md](T1-EXECUTION-DISTRIBUTION.md))  
**Périmètre :** articulation des lots fonctionnels A, B, C et D ; préparation des arbitrages techniques avant développement  
**Dépôt :** sedirae/OSIA  
**Source de vérité des exigences :** les quatre documents de cadrage fonctionnel v1.0 validés le 05/11/2026, à importer dans ce dépôt avant approbation finale.

> **Limite de traçabilité :** les quatre consolidations Markdown des lots A–D ont été produites dans d'autres conversations mais leurs octets ne sont pas actuellement présents dans le dépôt et n'ont pas été accessibles en lecture intégrale lors de cette rédaction. Les principes documentés et décisions retrouvés ont été respectés ; aucune paraphrase de ce document ne remplace leurs textes validés. La confrontation exigence par exigence avec les quatre originaux reste un préalable à la validation technique v1.0.

## 1. Objectifs, périmètre et méthode

OSIA accélère une investigation OSINT sur des informations publiques, relie des entités, propose des approfondissements, qualifie les sources et restitue résultats, preuves et contradictions. Son moteur ne doit ni inventer des relations ni engager des dépenses imprévues. L'investigateur garde la maîtrise des paramètres, des branches, des décisions de validation et des transmissions externes.

Cette proposition distingue systématiquement :
- **VALIDÉ (fonctionnel) :** exigence explicitement actée dans les lots A–D.
- **PROPOSÉ (technique) :** implémentation recommandée ci-dessous, à arbitrer.
- **OUVERT :** question structurante non tranchée.
- **REPORTÉ :** extension éventuelle, hors engagement V1.

L'objectif n'est pas de sélectionner tous les frameworks d'avance : d'abord arrêter les frontières et invariants, puis arbitrer le socle d'exécution, le stockage et la stratégie d'intégration.

## 2. Matrice de correspondance avec les lots A–D

| Origine | Principe fonctionnel connu | Responsabilités techniques principales |
| --- | --- | --- |
| A | Investigation progressive jusqu'à un nombre de liaisons borné, arbre de rebonds, objectif et preuves | Orchestrateur, planificateur, moteur de relations, suivi de profondeur |
| A5 — option D | Arrêt automatique quand la réponse est suffisamment étayée ; pistes restantes proposées ; poursuite uniquement sur action humaine, en nouvelle branche et sous limites explicites | Politique d'arrêt, plan de prolongation non exécuté, contrôle des budgets et de profondeur |
| B1–B3 — option C | Catalogue hybride extensible, sources internationales, accès API/web/documents/jeux de données/navigateur avancé autorisé | Registre de sources et adaptateurs, acquisition multimode |
| B4 — option C | IA de sélection **supervisée** par un moteur de règles indépendant | Sélecteur de sources, garde-fous et approbations |
| B5 — option C | Fiabilité multidimensionnelle | Évaluation par source, collecte, pièce de preuve et assertion ; contradictions visibles |
| B6 — option C | Gestionnaire centralisé des ressources et réservations | Quotas, budgets, réservations atomiques, limites techniques |
| B7 — option C | Maintenance autonome supervisée des connecteurs | Santé, diagnostics, tests, changements contrôlés |
| C | Synthèse, graphe d'entités, fiches, preuves, corrections et contradictions | Interface d'investigation et moteur de projections |
| C6 — option C | Validation humaine réversible, non destructive ; original conservé ; historique horodaté ; décision humaine distincte de l'étayage | Journal de décisions, projections recalculables |
| C7 — option C | Espace unifié et multi-branches ; arbre d'investigation distinct du graphe ; vue par branche et consolidée ; exports manuels versionnés | Modèle des branches, navigation, rapports, exports |
| D1 — option C | Données locales structurées, versionnées, résilientes | Base transactionnelle locale, migrations, reprise |
| D2 — option C | Plusieurs fournisseurs IA ; orchestration supervisée ; secrets non persistés par défaut | Registre de modèles, adaptateurs, gestion de secrets |
| D3 — option C | Profils et budgets hiérarchisés | Résolution des paramètres et gouverneur central |
| D4 — option C | Historique et preuves conservés ; cache technique distinct et purgeable | Stockage de preuves immuables, cache à TTL |
| D5 — option C enrichie | Archive portable .osia, restitution HTML autonome, restauration supervisée | Export/import versionné, rendu hors ligne |
| D6 — option C | Confidentialité native, coffre chiffré facultatif, filtrage des données sensibles, neutralisation des contenus actifs | Politique de confidentialité, gestion de clés, sanitation |
| D7 — option C | Paramètres hiérarchisés et résilience supervisée | Configuration, snapshots de cohérence, reprise, diagnostics |

Les sous-décisions A et C non visibles en intégralité dans les sources accessibles ne sont pas réattribuées à des numéros d'arbitrage précis. **Action documentaire requise :** importer les quatre fichiers A–D originaux et compléter les renvois et critères d'acceptation sans changer leur sens.

## 3. Architecture de référence (PROPOSÉE)

**Orientation recommandée : application local-first, cœur métier indépendant de l'interface, services modulaires dans un monolithe local plutôt que microservices.**

~~~text
Utilisateur
   |
   v
Interface React/TypeScript
  |-- Synthèse / fiches / décisions
  |-- Graphe d'entités
  |-- Arbre des investigations / branches
  |-- Budgets, sources, paramètres, exports
   |
   v   API locale contractuelle + événements de progression
Noyau OSIA (Python proposé)
  |-- Application / autorisations / profils
  |-- Planificateur + politiques d'arrêt
  |-- Orchestrateur durable + file de tâches
  |-- Gouverneur de ressources (budget, quotas, concurrence)
  |-- Sélecteur de sources : règles + suggestions IA
  |-- Registre des connecteurs + santé/maintenance
  |-- Acquisition (API, HTTP, document, dataset, navigateur)
  |-- Normalisation + résolution d'entités
  |-- Gestion assertions / preuves / contradictions
  |-- Journal des décisions humaines + projections
  |-- Multi-IA + accès aux secrets
  |-- Export/import .osia + HTML autonome
   |
   +---- Base transactionnelle locale et index de recherche
   +---- Stockage de contenus/preuves par empreinte
   +---- Cache de collecte purgeable
   +---- Traces techniques expurgées
   |
   +---- Fournisseurs IA externes UNIQUEMENT si configurés
   +---- Sources publiques externes selon droits et politiques
~~~

Le noyau est la seule autorité pour la dépense, la persistance, le lancement d'actions réseau et les changements de statut. L'interface et les réponses d'un LLM expriment des **intentions**, jamais une permission d'exécution implicite.

### 3.1 Socle technique candidat (à arbitrer)

| Couche | Proposition | Motif | Statut |
| --- | --- | --- | --- |
| Interface | React + TypeScript | Composants et visualisations interactives | PROPOSÉ |
| API du noyau | Python + FastAPI + contrats JSON typés | Écosystème collecte, données et IA ; frontière explicite | PROPOSÉ |
| Exécution longue | Worker applicatif local avec file transactionnelle persistante | Pause, reprise, idempotence, budgets ; pas de dépendance cloud | PROPOSÉ |
| Données structurées | SQLite avec migrations transactionnelles et recherche FTS5 | Portabilité locale, ACID, recherche textuelle | PROPOSÉ |
| Pièces collectées | Répertoire de blobs adressés par SHA-256, manifestes dans SQLite | Intégrité, déduplication, traçabilité | PROPOSÉ |
| Cache | Stockage séparé avec TTL, invalidation par profil/source | Purge sans perte des preuves | PROPOSÉ |
| Automatisation web | Navigateur isolé via Playwright seulement dans les modes autorisés | Pages dynamiques et contrôle d'exécution | PROPOSÉ |
| Graphe | Bibliothèque graphique JS à sélectionner après prototype avec grands graphes | Exploration et filtrage interactifs | OUVERT |
| Distribution | Linux natif exclusivement ; moteur indépendant ; interface web V1 activable ; client GNOME/Rust ultérieur | Modes poste/serveur et interfaces indépendants | **VALIDÉ (T1.1–T1.7)** |
| Conteneurisation | Aucune distribution conteneurisée officielle en V1 ; outils internes de développement non prescrits | Installation Linux native choisie | **VALIDÉ (T1.3)** |

**Non-retenu par défaut :** cloud obligatoire, comptes externes imposés, synchronisation implicite, microservices/Redis/broker pour une instance mono-utilisateur, base graphe distante ou SaaS d'analytique. Ce ne sont pas des interdictions futures ; chaque ajout nécessiterait un besoin avéré.

### 3.2 Découpage modulaire

- **core/domain :** investigation, branche, entité, relation, assertion, preuve, décision, événements. Aucune dépendance à React, à un fournisseur IA ou à un site web.
- **core/policies :** profondeur, limites de ressources, autorisations de source, arrêt, sécurité et confidentialité.
- **application :** commandes, cas d'usage, projections, reprise, transactions.
- **adapters/sources :** chaque connecteur implémente le même contrat de capacités, validation, collecte, transformation et diagnostic.
- **adapters/ai :** modèles, tarification, plafonds et normalisation des réponses structurées.
- **adapters/storage :** SQLite, index, fichiers de preuve, cache, exports.
- **api :** validation de schémas et diffusion d'événements ; aucune logique métier propriétaire.
- **ui :** graphes, arbre, fiches, tableau de bord de budget et approbations.
- **tests/contracts :** jeux de données factices, connecteurs simulés et non-régression.

Dépendance voulue : les adaptateurs dépendent des interfaces du domaine ; le domaine ne connaît pas les adaptateurs.

### 3.3 Choix d'exécution et de distribution **VALIDÉS** (lot T1)

Le lot **T1 — Architecture d'exécution et distribution** a été clôturé le 06/11/2026 : moteur Linux natif indépendant du frontend ; frontend web V1 activable ; client natif GNOME en Rust/GTK 4/gtk-rs/libadwaita **reporté** ; installation native unifiée avec configuration poste/serveur ; API REST + SSE ; mises à jour manuelles avec notifications ; accès distant activable explicitement et protégé. **Ne pas assimiler « frontend web désactivé » à « API désactivée ».**

Les décisions détaillées, limites de la V1, points non arbitrés et critères de recette sont la source de vérité de ce lot : **[T1-EXECUTION-DISTRIBUTION.md](T1-EXECUTION-DISTRIBUTION.md)**. Les technologies proposées par ailleurs dans ce document restent des hypothèses tant qu'un arbitrage distinct ne les valide pas.

## 4. Cycle d'investigation

### 4.1 États durables

Investigation : BROUILLON → PRÊTE → ACTIVE → PAUSÉE / ATTENTE_APPROBATION → TERMINÉE / ARRÊTÉE / EN_ERREUR.  
Branche : PROPOSÉE → APPROUVÉE → EN_COURS → SUSPENDUE → TERMINÉE / ANNULÉE / EN_ERREUR.  
Tâche : PLANIFIÉE → RÉSERVÉE → EN_COURS → RÉSULTAT_ENREGISTRÉ → TERMINÉE, ou ÉCHEC / ANNULÉE.

Une branche proposée **n'implique pas** l'exécution d'une requête ou d'un appel IA. Toute continuation après l'objectif, ou au-delà de la profondeur initiale, est une nouvelle branche approuvée avec limites explicites.

### 4.2 Pipeline proposé

1. **Entrée :** objectif, entités de départ, profil de recherche, profondeur, limites, règles de confidentialité.
2. **Planification :** propositions de pistes et sources ; détection de doublons, cycles et résultats déjà disponibles.
3. **Filtrage indépendant :** règles d'admissibilité, autorisations, coût, risque, disponibilité et limites.
4. **Préautorisation :** présentation des actions/budgets si leur lancement exige un accord ; réservation avant toute opération payante.
5. **Acquisition :** collecte autorisée, capture des métadonnées, empreinte, statut et provenance.
6. **Extraction :** assertions candidates et entités proposées avec citations précises de leurs preuves.
7. **Rapprochement :** identités candidates évaluées, sans fusion automatique irréversible.
8. **Analyse :** liens, contradictions, lacunes, niveau d'étayage et pistes alternatives.
9. **Évaluation d'arrêt :** objectif suffisamment étayé → arrêt de la branche ; suggestions non exécutées.
10. **Restitution :** synthèse, graphe, arbre, sources, incertitudes et historique des actions humaines.

### 4.3 Profondeur, cycles et réutilisation

**Proposition de définition à valider :** une profondeur correspond à un saut relationnel depuis l'entité graine au sein du chemin de branche. Une consultation supplémentaire de source, une tentative échouée ou une nouvelle formulation d'une même entité ne crée pas automatiquement un saut. Distinguer profondeur du parcours, nombre total de liens du graphe, et profondeur autorisée pour chaque branche.

Conserver la filiation des branches et leurs paramètres figés au lancement. Réutiliser une preuve déjà collectée si elle reste pertinente, avec la mention de son ancienneté et sa date ; ne pas la facturer comme une nouvelle requête. Les cycles et les relations déjà visitées sont détectés avant lancement de nouveaux travaux.

### 4.4 Arrêt automatique et relance humaine

L'arrêt ne doit pas être décidé par la seule « conviction » d'un LLM. Le moteur d'arrêt confronte la question aux assertions, aux sources réellement consultées, aux contradictions et aux critères de suffisance configurés. En cas de doute, restitution des incertitudes ; jamais déclaration de preuve obtenue sans source. La poursuite est proposée avec ses ressources estimées, sans appel payant anticipé.

## 5. Gestion des sources, de l'IA et des coûts

### 5.1 Contrat de connecteur

Chaque connecteur expose de manière versionnée : identifiant, provenance et juridiction, types d'entités/sources couverts, modes d'accès, schéma des entrées/sorties, limites de débit et pagination, coût éventuel, besoins d'identification, politique de cache, capacités de test, état de santé, conditions d'utilisation et niveau d'autorisation.

Les adaptateurs produisent une **enveloppe de collecte** commune : date UTC, URL ou identifiant de jeu de données, connecteur/version, méthode, réponse source ou référence de capture, empreinte, licence/conditions connues, erreurs et éventuelle péremption. Un document ne doit pas être confondu avec l'affirmation extraite de ce document.

### 5.2 IA sous supervision

- La sélection de sources combine **règles exécutables indépendantes** et propositions IA ; la liste effective de sources reste validée par les politiques.
- L'IA peut extraire, proposer des rapprochements, rédiger ou classer des pistes ; elle ne peut pas autoriser une dépense, une transmission, une action navigateur ou une fusion destructive.
- Tous les fournisseurs exposent un contrat commun d'estimation, exécution, limites, usages et erreurs.
- Les demandes structurées sont validées côté noyau ; une sortie invalide est rejetée ou présentée comme non structurée, jamais assimilée à un fait.
- Conserver le modèle, la version si connue, l'horodatage et la référence du prompt technique sans enregistrer les secrets. L'historique de prompt brut reste soumis au niveau de confidentialité.

### 5.3 Gouverneur de ressources — invariant critique

Toute action à impact mesurable traverse un **seul service de réservation**. Limites hiérarchiques : installation/profil → investigation → branche → source/connecteur/fournisseur. La contrainte la plus restrictive prime ; aucune valeur par défaut ne peut relever silencieusement un plafond.

~~~text
Action proposée
  -> test d'autorisation et d'éligibilité
  -> calcul de borne de coût/volume/durée
  -> réservation atomique en base (idempotency_key)
  -> exécution contrôlée et plafonnée
  -> comptabilisation réelle ou prudente
  -> libération du reliquat uniquement après rapprochement
  -> événement d'audit et mise à jour des compteurs
~~~

Prévoir plafonds monétaires, tokens, appels, pages, octets, profondeur, temps, parallélisme et débit par source. Une tarification inconnue ou un majorant non fiable interdit l'exécution payante automatique : demande de validation spécifique ou chemin alternatif gratuit.

Les erreurs, retries, annulations et crashs ne doivent ni doubler la dépense prévue ni réinitialiser les réservations. Un appel externe dont l'issue est inconnue après interruption reste **coût potentiellement engagé** tant que sa facturation n'est pas réconciliée. Ne pas promettre que tous les fournisseurs garantissent une idempotence réseau.

### 5.4 Gouvernance et maintenance des connecteurs

Checks de santé distincts de la collecte réelle, tests sans facturation par défaut, journal des versions d'adaptateur, diagnostic d'évolution des pages, désactivation ciblée, propositions de correction supervisées. Ne jamais auto-déployer une modification de connecteur qui élargirait droits, dépenses ou données transmises.

## 6. Données, preuves, graphe et décisions

### 6.1 Modèle conceptuel proposé

- **investigations** : objectif, statut, profil figé, budgets, création.
- **branches** : parent, origine, justification, profondeur et budgets approuvés.
- **jobs / task_attempts** : exécutions et reprises, clés d'idempotence, état et causes d'échec.
- **source_catalog / connectors / source_observations** : sources, adaptateurs, visites et provenance.
- **evidence_blobs** : documents/captures originaux, empreintes, mime, taille, horodatages, politique de rétention.
- **entities / entity_aliases** : identités et attributs avec degré de certitude ; ne pas inférer identité sur un simple nom.
- **assertions / relations / assertion_evidence** : déclarations et liens distincts des pièces justificatives, sens, contexte et statut d'étayage.
- **contradictions** : paires ou groupes d'assertions incompatibles explicitement conservés.
- **human_decisions / domain_events** : validation, rejet, correction, fusion/séparation, justification optionnelle, auteur, date, annulation compensatoire.
- **cost_reservations / usage_ledger** : budget estimé, engagé, constaté, annulations et rapprochements.
- **settings / profiles / secrets_references** : hiérarchie des paramètres ; références de secrets et non valeur en clair par défaut.
- **cache_entries / exports / import_sessions** : caches techniques, manifestes, vérifications, restauration supervisée.

Chaque objet durable porte un identifiant stable, un numéro de version de schéma et les liens nécessaires à sa provenance. Les contenus binaires sont référencés par hash ; la déduplication ne doit pas effacer les différences de contexte de collecte.

### 6.2 Règles d'intégrité

1. Aucune assertion factuelle « étayée » sans au moins une référence de preuve consultable (ou mention explicite qu'elle n'est pas vérifiée).
2. Aucune preuve originale modifiée par une correction humaine ; annotation et projection séparées.
3. Aucune fusion d'entités irréversible : conserver aliases, correspondances, versions et possibilité de séparation.
4. Un statut « accepté par l'utilisateur » n'équivaut pas automatiquement à « vérifié dans les sources ».
5. Une contradiction reste accessible après consolidation, même si une hypothèse est privilégiée.
6. Une suppression de cache n'efface jamais, par effet de bord, une preuve conservée dans le dossier d'investigation.
7. Les projections synthèse/graphe/rapports sont reconstructibles depuis données et décisions versionnées.

### 6.3 Historique sans corruption

Préférer un **journal métier append-only** complété de projections matérialisées remises à jour transactionnellement. Une annulation ajoute un événement compensatoire plutôt que supprimer la décision passée. L'exécution de nouveau d'une projection ou d'un rapport ne doit pas appeler un fournisseur IA sans budget autorisé ; si une régénération IA est nécessaire, afficher la demande au lieu de facturer.

## 7. Interface, navigation et restitution

L'espace d'investigation comprend deux systèmes de navigation **non interchangeables** :
- **Graphe d'entités** : relations sémantiques, origine, attributs, contradictions et qualité de preuve.
- **Arbre d'investigations** : historique des branches, rebonds autorisés, états, objectifs, profondeurs et budgets propres.

Fiches et panneaux de preuves doivent permettre de remonter à l'observation et, lorsque disponible, au passage exact ou à la capture originale. Afficher séparément : source, confiance/étayage, décision humaine, fraîcheur, provenance de branche.

La vue consolidée déduplique avec prudence et conserve les contradictions. Les rapports synthétiques et détaillés sont générés dans le périmètre explicite de la branche ou de la consolidation, avec numéro de version et export uniquement à l'initiative de l'utilisateur.

**API de principe, non contractuelle tant que le socle n'est pas validé :**

~~~text
POST /investigations               créer un dossier
POST /investigations/{id}/plan     proposer un plan sans l'exécuter
POST /branches/{id}/approve        approuver limites et paramètres
POST /runs/{id}/start              exécuter si autorisé
POST /runs/{id}/pause              pause sûre
POST /runs/{id}/cancel             annuler sans effacer l'historique
GET  /investigations/{id}/tree     arbre des branches
GET  /investigations/{id}/graph    projection graphe
GET  /evidence/{id}                preuve et provenance
POST /decisions                    correction/validation/annulation humaine
GET  /budgets/{scope}              réservations, engagés et restants
POST /exports                      créer un export demandé
POST /imports/preview              contrôle avant restauration
POST /imports/commit               restauration approuvée
GET  /events                       flux local de progression
~~~

Aucun endpoint de lecture ne doit provoquer d'appel IA facturable ou déclencher une collecte. Les opérations de lecture restent sûres et sans effet de bord.

## 8. Données locales, archives et résilience

### 8.1 Organisation de stockage (PROPOSÉE)

~~~text
OSIA_DATA/
  state/          base, migrations, checkpoints, verrou instance
  evidence/       originaux et métadonnées liés au dossier
  cache/          réponses temporaires purgeables
  exports/        archives et HTML explicitement générés
  backups/        sauvegardes contrôlées
  logs/           journaux techniques expurgés et bornés
~~~

Utiliser des transactions atomiques, intégrité référentielle, migrations versionnées réversibles quand possible, snapshots cohérents et vérification de restauration. Le mode WAL SQLite doit être intégré à la méthode de sauvegarde ; copier seulement le fichier principal pendant une session active ne suffit pas à garantir un snapshot cohérent. Préférer une sauvegarde via API de copie cohérente (Online Backup API ou mécanisme équivalent) et vérifier aussi les pièces externes référencées.

### 8.2 Archive .osia

**Exigence validée :** archive portable, versionnée, intégrité vérifiable et restauration supervisée. **Format interne proposé :** enveloppe versionnée contenant manifeste, données structurées, décisions, preuves choisies, hachages, périmètre et exclusions. Mode optionnel chiffré avec dérivation robuste depuis phrase de passe ; algorithmes/format à choisir après étude de compatibilité et migration.

À l'import : vérifier signature de format, taille et expansion maximales, chemins autorisés, empreintes, version de schéma, doublons et conflits ; présenter un aperçu et les choix de fusion avant écriture. Empêcher path traversal, écrasement de fichiers et exécution de code contenu dans l'archive. Aucun secret API inclus par défaut.

### 8.3 Restitution HTML autonome

Un fichier ou dossier transportable, lisible hors connexion, comprenant synthèse, tableaux, graphe ou représentation de repli, références de preuves exportables et contradictions. Aucun appel externe ni collecte au chargement. Toutes les données provenant de sources externes sont échappées/neutralisées ; si du JavaScript de présentation est embarqué, il appartient à l'application et non au contenu collecté, et une lecture dégradée sans JS doit rester possible. Sélection et occultation de données sensibles avant génération.

### 8.4 Reprise après incident

Reprise depuis le dernier état transactionnel cohérent. Réconcilier avant ré-exécution des actions potentiellement facturées ; marquer celles dont l'issue est indéterminée et demander arbitrage au besoin. Séparer « mise en pause », « abandon d'une branche », « purge du cache », « suppression d'un dossier » et « révocation de secret » : leurs effets ne sont pas interchangeables.

## 9. Sécurité, confidentialité et cadre d'utilisation

- **Local-first :** rien ne part vers un service de synchronisation par défaut ; seuls les connecteurs/fournisseurs explicitement configurés effectuent des requêtes autorisées.
- **Secrets :** clés en mémoire/session par défaut, coffre chiffré facultatif, jamais dans le frontend, une archive standard, un journal ou un rapport.
- **Contrôle de transmission :** afficher quels champs partent vers quels services et quel fournisseur est utilisé ; masquage/consentement selon politique et sensibilité.
- **Collecte :** privilégier sources publiques, API officielles, pagination et quotas. Aucun contournement automatique de CAPTCHA, authentification, paywall ou protection technique. Le navigateur avancé reste conditionné à une autorisation et aux politiques applicables.
- **Isolation :** documents web, réponses API et prompts de sources sont non fiables ; jamais interpréter leurs instructions comme commandes OSIA. Analyser le contenu en mode données, neutraliser HTML/scripts, limiter fichiers et téléchargements.
- **Réseau :** filtrage des destinations et redirections, contrôle SSRF, limites tailles/durées, refus par défaut des destinations privées/locales dans les connecteurs web génériques (sauf configuration explicite).
- **Interface locale :** si API sur loopback, authentification/jeton de session, contrôle d'origine et anti-CSRF, sans exposition LAN implicite. Politique de permissions minimale si emballage desktop.
- **Audit :** journaliser changements d'autorisation, dépense, décisions et exports, sans données sensibles inutiles ; purge configurable des traces techniques.
- **Effacement :** guidé, avec présentation des effets sur dossier, branches, preuves, exports et sauvegardes ; ne jamais promettre effacement des copies déjà exportées.

La qualification juridique de « public » ne suffit pas à elle seule à autoriser une collecte systématique : contraintes des sources, données personnelles et conditions d'accès doivent être prises en compte.

## 10. Qualité, observabilité et recette

**Contrôles unitaires :** hiérarchie de paramètres, politique d'arrêt, calcul de profondeur, dédoublonnage, qualité/provenance, résumé des coûts.  
**Contrats :** connecteurs simulés (API HTTP, page HTML, documents, dataset, navigateur), validateurs des sorties IA et schémas d'export.  
**Intégration :** transactions, reprise de tâche après crash, concurrence sur réservations, journal de décisions et restaurations.  
**E2E :** navigation branches/graphe, preuves, corrections, rapport HTML hors réseau.

**Cas de recette transversaux prioritaires :**
1. Source inaccessible : arrêt localisé et preuve d'erreur, sans bloquer les autres branches.
2. API payante rejetée après réservation : comptabilisation et restitution correctes, pas de double appel aveugle.
3. Deux actions concurrentes ne dépassent jamais le plafond commun.
4. Profondeur maximale atteinte : aucune nouvelle liaison exécutée automatiquement.
5. Objectif atteint à profondeur faible : arrêt automatique, suggestions non exécutées, nouvelle branche après validation.
6. Réponse IA inventant un lien : aucune assertion considérée comme prouvée sans source.
7. Deux sources contradictoires : les deux preuves et les réserves sont visibles.
8. Correction, fusion puis annulation : originaux intacts et projections cohérentes.
9. Cache purgé : dossier, preuves et historique conservés.
10. Fermeture brutale en cours de collecte : reprise contrôlée, aucun coût présumé gratuit.
11. Secret non persisté : aucune valeur dans l'archive ni le log.
12. Export HTML consulté sans réseau : restitution lisible sans transmission.
13. Archive corrompue ou archive malveillante : rejet sans écrire dans le dossier existant.
14. Import valide : prévisualisation, conflits, approbation et restauration vérifiable.
15. Changement de fournisseur : paramètres, tarification et politique de transmission revérifiés.

Les vérifications doivent porter sur des jeux synthétiques/reproductibles. Les tests live de connecteurs payants sont opt-in et budgétés. Pas de déclaration « testé » tant que les commandes et preuves n'existent pas.

## 11. Séquencement proposé

| Étape | Résultat mesurable | Dépendances |
| --- | --- | --- |
| T0 — Consolidation documentaire | Importer A/B/C/D v1.0 et relier exigences, critères et questions ouvertes | Fichiers sources |
| T1 — Socle et données | API locale, DB versionnée, opérations domaine, tests transactionnels | Arbitrage de l'exécution |
| T2 — Budgets et moteur | File durable, réservations, règles, parcours de branches et arrêt | T1 |
| T3 — Collecte + preuve | Deux connecteurs hétérogènes factices/réels gratuits, provenance et cache | T2 |
| T4 — IA et analyse | Contrat multi-modèles, extraction structurée, rapprochements et contradictions | T3 |
| T5 — Interface complète | Arbre, graphe, fiches, corrections, budgets et synthèses | T2–T4 |
| T6 — Portabilité et durcissement | .osia, HTML autonome, coffre facultatif, restauration, tests de sécurité | T1–T5 |

Chaque étape est une **proposition de séquencement**, pas une date ni une autorisation de développement.

## 12. Arbitrages techniques à ouvrir

| ID | Arbitrage | Options à comparer | Statut |
| --- | --- | --- | --- |
| T1 | [Exécution et distribution](T1-EXECUTION-DISTRIBUTION.md) | Linux natif, modes poste/serveur, frontend web V1, GTK ultérieur, REST + SSE, mises à jour manuelles | **VALIDÉ** |
| T2 | Stockage et sauvegarde | SQLite + blobs ; variantes de bases locales ; stratégie de chiffrement au repos | OUVERT |
| T3 | Langage et structure du noyau | Python modulaire ; TypeScript intégral ; noyau polyglotte | OUVERT |
| T4 | Orchestrateur durable | File transactionnelle maison contrôlée ; framework d'orchestration ; broker séparé | OUVERT |
| T5 | Sécurité des connecteurs et navigateur | Processus isolés ; conteneurs facultatifs ; isolation graduée par capacités | OUVERT |
| T6 | Graphe, résolution d'identités et confiance | Projection relationnelle, indices structurés, méthodes de score explicables | OUVERT |
| T7 | Formats .osia, HTML autonome et chiffrement | Schéma, compatibilité, restauration, rendu hors ligne | OUVERT |
| T8 | Contrats IA et gouverneur de coûts | Estimation prudente, tarifications, renouvellement des clés, profils et quotas | OUVERT |

**T1 clôturé et validé.** Les détails restant ouverts dans son document (format de paquet, authentification, TLS, etc.) ne remettent pas en cause les choix de principe. Les arbitrages structurants T2–T8 restent ouverts.

## 13. Conditions pour valider une v1.0 technique

- [ ] Les quatre fichiers A–D v1.0 originaux sont importés et identifiés comme références validées.
- [ ] Chaque décision et critère des quatre lots possède un renvoi vers un composant et un test.
- [ ] Les arbitrages techniques structurants T1–T8 ont un statut explicite.
- [ ] Le budget est gouverné **avant** tout appel externe et testé en concurrence/reprise.
- [ ] Les preuves restent indépendantes des interprétations IA et décisions humaines.
- [ ] La navigation arbre/graphe et les exports respectent les distinctions de périmètre.
- [ ] La sécurité et les politiques de transmission sont vérifiables.
- [ ] Le document technique n'est plus présenté comme validé seulement parce qu'il est commité.

## 14. Références d'implémentation consultées (indicatives)

- Tauri v2 — architecture et permissions : https://v2.tauri.app/concept/architecture/ ; https://tauri.app/security/capabilities/
- SQLite — WAL et FTS5 : https://sqlite.org/wal.html ; https://www.sqlite.org/fts5.html ; https://www.sqlite.org/backup.html
- Playwright Python — automatisation navigateur : https://playwright.dev/python/docs/intro
- FastAPI — limites des simples tâches d'arrière-plan pour les travaux lourds : https://fastapi.tiangolo.com/tutorial/background-tasks/

Ces références techniques étayent des **possibilités**, pas la validation de cette pile. La documentation fonctionnelle A–D prévaut sur toute commodité de framework.
