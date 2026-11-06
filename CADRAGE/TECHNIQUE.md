# OSIA — Architecture technique consolidée

**Édition 1.1 — 06/11/2026.** Décisions acquises et responsabilités ; pas un schéma SQL, une OpenAPI ou un verrouillage de dépendances déjà validés.

## 1. Choix structurants

| Domaine | Choix retenu | Référence |
| --- | --- | --- |
| Plateforme et distribution | Linux natif, distribution commune, modes Desktop/Server, frontend web installable facultativement | T1, T3.3 |
| Moteur | Python ; monolithe modulaire évolutif | T3.1–T3.2 |
| Exécution | E/S asynchrones, processus pour charge ou isolation ; moteur autonome | T3.3–T3.5 |
| Données | PostgreSQL principal ; binaires/preuves séparés ; déduplication SHA-256 | T2.1–T2.4 |
| Ordonnancement | Tâches durables et coordination PostgreSQL | T4.2 |
| Graphe | Modèle logique PostgreSQL, identifiants stables, vues contextuelles | T6 |
| Interfaces | REST et SSE ; contrats typés/versionnés | T1, T3.7, T4.9 |
| Navigateur avancé | Playwright isolé, uniquement si nécessaire et autorisé | T5.3 |
| IA | Courtier central multi-fournisseurs ; sorties structurées vérifiées | T8.1, T8.6 |
| Coûts | Politiques indépendantes ; réservations transactionnelles ; réconciliation | B6, T3.11, T8.4 |
| Archives | Orientation ZIP64, JSON/JSONL, documents originaux ; manifeste SHA-256 | T7.1–T7.2 |
| Chiffrement d'archive | Facultatif, authentifié ; Argon2id pour phrase secrète ; AES-256-GCM cité comme exemple du choix recommandé | T7.3 |
| Client natif futur | Rust/GTK4/libadwaita, distinct du moteur, différé | T1, T3 §1 |

Redis, RabbitMQ, Celery, Neo4j, Docker/Podman et des microservices distribués ne sont pas des prérequis V1. Aucune pile frontend, bibliothèque ORM, version de Python/PostgreSQL, ni fournisseur IA exclusif n'a été sélectionné par cette consolidation.

## 2. Responsabilités

| Composant logique | Responsabilité et frontière |
| --- | --- |
| Entrées CLI/API/service | Valider les demandes et le contexte d'accès ; déléguer le métier au moteur |
| Orchestrateur et planificateur | Plan, sous-objectifs, tâches, priorités, branches, arrêts ; conserver les révisions |
| Politiques et budgets | Autoriser/refuser indépendamment de l'IA ; permissions, quotas, restrictions, bornes et réservations |
| Ordonnanceur/exécuteurs | Exécuter les tâches admissibles ; concurrence bornée ; reprise et annulation contrôlées |
| Connecteurs | Exposer capacités déclarées ; collecte et provenance selon les accès permis |
| Courtier IA | Sélection de modèles autorisés, appels, schémas, coûts et replis ; aucune voie parallèle d'appel modèle |
| Pipeline | Collecter, normaliser, extraire, proposer relations, évaluer, intégrer et restituer en conservant la provenance |
| Graphe et décisions | Identités, assertions, relations, contextes, contradictions, décisions réversibles et impacts |
| Persistance | État cohérent en PostgreSQL et fichiers ; migrations, intégrité et récupération |
| Restitution/import/export | Vues, synthèses versionnées, archives et HTML ; import contrôlé |

Ces frontières sont logiques. Elles n'imposent ni un service réseau ni une sérialisation JSON pour chaque appel Python interne. Les traitements isolés utilisent des frontières adaptées à leurs permissions.

## 3. Invariants transversaux

| Identifiant | Invariant | Références |
| --- | --- | --- |
| OSIA-I-01 | L'IA propose ; les politiques autorisent. Aucun contenu collecté ne devient une instruction d'exécution | B4, T3.11, T5.6, T8.1 |
| OSIA-I-02 | Chaque opération payante réserve un budget autorisé avant départ, y compris reprise, repli, maintenance et tests de connexion | B6/B7, D2, T8.4 |
| OSIA-I-03 | Un objectif atteint arrête l'exploration ; une suite est proposée, puis lancée explicitement dans une branche liée | A5, C7, T4.6 |
| OSIA-I-04 | Profondeur, volume, temps, concurrence et coûts restent contrôlés indépendamment de l'IA | A.9, T4.8 |
| OSIA-I-05 | Provenance, temporalité, originaux conservables et contradictions survivent aux corrections non destructives | B5, D4, T6 |
| OSIA-I-06 | Étayage et décision humaine restent indépendants ; les correspondances ambiguës ne sont pas fusionnées automatiquement | C6, T6.4–T6.7 |
| OSIA-I-07 | Les objectifs et décisions contextuels restent distincts dans le graphe commun | A9, T6.8 |
| OSIA-I-08 | Une synthèse stabilisée touchée est signalée puis actualisée sur demande, sans réécriture silencieuse | A11, C3, C7 |
| OSIA-I-09 | Aucun rejeu aveugle d'appel externe incertain ; aucune libération d'enveloppe fondée seulement sur une interruption locale | D7, T3.6, T4.7, T8.4 |
| OSIA-I-10 | PostgreSQL et preuves sont cohérents à l'écriture, à la sauvegarde et à la restauration | T2.4, T2.6 |
| OSIA-I-11 | Le mode serveur protège API et données même sans frontend ; exposition distante explicite et HTTPS | T5.7 |
| OSIA-I-12 | Pas de secrets dans prompts, journaux, diagnostics, archives ou exports de paramètres | D2, T5.5, T8.8 |
| OSIA-I-13 | Import et consultation HTML ne déclenchent aucune nouvelle recherche ni dépense IA | D5, T7 |
| OSIA-I-14 | Aucune preuve utile n'est supprimée pour purger le cache ou récupérer automatiquement de l'espace | D4, T2.8 |
| OSIA-I-15 | Une alternative de source/modèle respecte l'autorisation de transmission et le budget déjà accordés | D2, T8.9 |
| OSIA-I-16 | L'interface ne porte ni état métier faisant autorité ni possibilité de contourner les règles du moteur | T1, T2, T3 |

## 4. État, concurrence et reprise

Conserver investigations, branches, tâches et dépendances, plan et révisions, paramètres effectifs, autorisations, réservations, appels externes, résultats, erreurs et décisions. Un journal complète l'état sans imposer un event sourcing intégral.

Le mécanisme de concurrence doit empêcher deux tâches de consommer la même enveloppe. L'état d'une opération doit distinguer au minimum le projet d'appel, l'autorisation/réservation, l'appel en cours, son résultat connu ou incertain et sa réconciliation ; les noms d'états et transitions exacts restent à spécifier.

Après interruption, réconcilier avant de réémettre. Un timeout ou une annulation côté OSIA peut coexister avec un traitement/facturation externe déjà engagé. Aucun mécanisme ne doit promettre une sémantique « une seule fois » chez un fournisseur sans garantie établie.

Les limites s'appliquent simultanément : global mensuel, profil effectif, investigation, branche, fournisseur, modèle, opération et ressources de l'hôte. Un profil ne desserre pas les plafonds supérieurs. L'augmentation d'un plafond n'autorise pas implicitement une nouvelle branche. Le fuseau, la période et les règles de clôture mensuelle doivent être spécifiés.

## 5. Fin d'exploration et synthèse

Arrêter l'exploration interdit de lancer de nouvelles pistes, y compris si du budget reste. La restitution finale peut utiliser les acquis ; une génération IA nécessaire reste une opération facturable sous enveloppe autorisée. La conception doit prévoir ce besoin dans le plan/budget initial. Si aucun appel autorisé n'est possible, les résultats et la dernière synthèse disponibles restent consultables avec leur statut ; aucune réserve spéciale illimitée n'est créée.

Cette règle articule A5, C3-05, D3 et T8.4 : produire une restitution n'est pas une permission d'outrepasser un plafond.

## 6. Stockage et sauvegarde

PostgreSQL porte métadonnées, contexte et graphe. Les fichiers portent les preuves et binaires ; SHA-256 permet détection d'identité de contenu et contrôle d'intégrité. Dédupliquer les octets ne fusionne ni les sources, ni les dates de collecte, ni les droits de réutilisation.

Le protocole d'écriture et de récupération coordonne base et fichiers. Une transaction SQL seule ne couvre pas le système de fichiers. Les sauvegardes à chaud capturent une vue cohérente de la base et des fichiers correspondants, avec manifeste et contrôle, sans exiger un arrêt complet de l'application. Le mécanisme PostgreSQL précis reste à concevoir.

Distinguer configuration, données durables, cache, journaux et sauvegardes dans des emplacements Linux personnalisables. Les données sensibles temporaires et sauvegardées sont incluses dans le périmètre de protection choisi. Le coffre éventuellement persistant nécessite une politique spécifique de sauvegarde/récupération ; cela ne lève jamais l'exclusion des secrets des archives portables.

## 7. Sécurité et frontières de confiance

Connecteurs officiels prioritaires ; manifestes déclarant capacités, permissions, domaines, dépendances et coûts. Les niveaux officiel, tiers approuvé et expérimental commandent une isolation graduée. Un sous-processus n'est pas à lui seul une sandbox : utiliser les restrictions Linux adaptées.

Le contrôle réseau centralisé couvre destinations, redirections, adresses internes, quotas, délais et volumes. Les ressources privées/locales éventuellement autorisées par T5.4 servent un usage explicitement permis ; cela n'élargit pas implicitement le périmètre OSINT aux données privées. Les accès à un modèle local ou à un service configuré doivent rester distincts des destinations arbitraires trouvées dans une page.

Playwright est utilisé lorsque nécessaire, avec sessions isolées et téléchargements contrôlés. Aucun contournement de CAPTCHA ou d'accès. Les documents, archives et pages sont des entrées non fiables ; les traitements sensibles sont restreints. L'audit de sécurité T5.9 est distinct des journaux techniques T3.13, tous sans secrets et à conservation maîtrisée.

## 8. Graphe et connaissance

Modèle extensible d'entités à identifiants internes stables ; identifiants externes séparés. Relations typées, datées, orientées si nécessaire, sourcées et éventuellement concurrentes. Le modèle doit préserver les relations impliquant plusieurs objets prévues fonctionnellement, sans figer ici leur représentation SQL.

Les fusions/séparations conservent les entités et références d'origine. Les corrections recalculent les dépendances ciblées, pas toutes les conclusions par appels IA. Chargement progressif, indexation, limites des entités très connectées et vues par contexte assurent la croissance maîtrisée.

## 9. Archives, chiffrement et HTML

La spécification `.osia` doit définir manifestes, versions, données, dépendances, contrôles, exclusions et migrations conformément à ZIP64/JSON/JSONL. Le chiffrement intégral couvre aussi les noms internes et métadonnées sensibles ; la phrase secrète n'est pas stockée dans l'archive. Argon2id est retenu pour la dérivation ; le profil AEAD et sa sérialisation restent à fixer, AES-256-GCM étant donné comme exemple en T7.3. Aucune cryptographie maison n'est suggérée par ce cadrage.

SHA-256 ne prouve pas l'identité de l'auteur. La signature d'authenticité est facultative et distincte du chiffrement authentifié. Le rapport HTML privilégie un fichier autonome ; les pièces volumineuses peuvent nécessiter des fichiers associés sur choix explicite, tous disponibles hors ligne. Les scripts de restitution maîtrisés sont permis ; les scripts de sources et chargements tiers automatiques sont neutralisés.

## 10. Qualité et détails à concevoir

Tests unitaires, intégration, contrats, scénarios de bout en bout et non-régression avec connecteurs/IA simulés ; évaluation reproductible par tâche indépendante du fournisseur. Les journaux structurés sont requis ; métriques exhaustives et traces distribuées sont différées.

Voir [RECETTE.md](RECETTE.md) pour les scénarios, [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md) pour les décisions de réalisation et [SOURCES.md](SOURCES.md) pour la provenance. Ces documents n'attestent aucun test applicatif exécuté.
