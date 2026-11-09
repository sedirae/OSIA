# OSIA — Registre consolidé des décisions

**Édition 1.1 — 06/11/2026.** 101 arbitrages numérotés d’origine (A–D, T2–T8) et sept thèmes éditoriaux T1. Les options sont celles des sources ; aucune option nouvelle n’est inventée. Les critères sont décrits dans [RECETTE.md](../CADRAGE/RECETTE.md).

## Portée

Les décisions détaillées figurent dans les lots liés. Les résumés ci-dessous ne retranchent pas leurs exceptions, règles et scénarios. Les sources `SRC-*` sont définies dans [SOURCES.md](../CADRAGE/SOURCES.md). Les dates de validation sont le 05/11/2026 pour A–D et le 06/11/2026 pour les lots techniques. La date de consolidation n’est pas une nouvelle validation produit.

T1 : `EXEC-*` regroupe des principes corroborés par les lots ultérieurs et le contexte de conversation ; ces sept lignes ne prétendent pas reproduire la correspondance originale T1.1–T1.7. Voir [T1.md](../CADRAGE/LOTS/T1.md).

## Périmètre de livraison V1

Le porteur a validé l’ensemble des six décisions le 06/11/2026. Leurs formulations et les valeurs associées sont dans [PERIMETRE-V1.md](../CADRAGE/PERIMETRE-V1.md).

| Identifiant | Objet |
| --- | --- |
| V1.1 | Fonctions livrées et reports |
| V1.2 | Connecteurs initiaux |
| V1.3 | Fournisseurs et modèles IA |
| V1.4 | Profils, limites et arrêt |
| V1.5 | Interopérabilité |
| V1.6 | Charte visuelle |

## A

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [A1](../CADRAGE/LOTS/A.md) | Option A : investigation automatique, sans validation à chaque rebond | SRC-A | S03, S13, REC-X-02 |
| [A2](../CADRAGE/LOTS/A.md) | Option B : conserver sans approfondir automatiquement | SRC-A | S14 |
| [A3](../CADRAGE/LOTS/A.md) | Hybride A/B : nouvelle branche rattachée à l'investigation, héritant des résultats et du contexte | SRC-A | S09, REC-C-15 |
| [A4](../CADRAGE/LOTS/A.md) | Option B : priorité à l'objectif, découverte périphérique permise | SRC-A | S01, S02 |
| [A5](../CADRAGE/LOTS/A.md) | Option D : arrêt automatique + suggestions d'approfondissement, poursuite uniquement sur décision utilisateur | SRC-A | S08, S09, B-ACC-15 |
| [A6](../CADRAGE/LOTS/A.md) | Conserver les versions et examiner leurs écarts, notamment temporels | SRC-A | S11 |
| [A7](../CADRAGE/LOTS/A.md) | Dynamique, sans validation intermédiaire obligatoire | SRC-A | S01, S14 |
| [A8](../CADRAGE/LOTS/A.md) | Plusieurs sous-objectifs compris depuis une phrase unique | SRC-A | S15 |
| [A9](../CADRAGE/LOTS/A.md) | Données sourcées communes ; objectifs et conclusions indépendants | SRC-A | S06, S07, REC-C-16 |
| [A10](../CADRAGE/LOTS/A.md) | Propagation automatique des impacts, sans appel API systématique | SRC-A | S06, S07 |
| [A11](../CADRAGE/LOTS/A.md) | Signalement + actualisation de la synthèse sur demande | SRC-A | S12, REC-X-03 |
| [A12](../CADRAGE/LOTS/A.md) | Graphe commun avec filtres par branche | SRC-A | REC-C-16 |

## B

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [B1](../CADRAGE/LOTS/B.md) | C — Architecture hybride : connecteurs préintégrés sur un socle modulaire | SRC-B | B-ACC-01, B-ACC-02 |
| [B2](../CADRAGE/LOTS/B.md) | C — Catalogue international évolutif, généraliste, sans frontière géographique structurelle | SRC-B | B-ACC-03 |
| [B3](../CADRAGE/LOTS/B.md) | C — Accès multimode adaptatif : API, recherche web, extraction, documents et données ouvertes, navigateur avancé si justifié | SRC-B | B-ACC-03, B-ACC-04 |
| [B4](../CADRAGE/LOTS/B.md) | C — Sélection hybride supervisée : choix proposés par l'IA, exécution conditionnée par un contrôleur indépendant | SRC-B | B-ACC-05, B-ACC-06, B-ACC-15, B-ACC-16 |
| [B5](../CADRAGE/LOTS/B.md) | C — Fiabilité multidimensionnelle et explicable : éléments de preuve et critères distincts | SRC-B | B-ACC-07, B-ACC-08, B-ACC-09 |
| [B6](../CADRAGE/LOTS/B.md) | C — Gestionnaire centralisé avec réservations : suivi des coûts, quotas, appels simultanés et limites | SRC-B | B-ACC-10, B-ACC-11, B-ACC-12 |
| [B7](../CADRAGE/LOTS/B.md) | C — Maintenance autonome supervisée : détection, diagnostic, corrections encadrées, validation des changements sensibles | SRC-B | B-ACC-13, B-ACC-14 |

## C

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [C1](../CADRAGE/LOTS/C.md) | Option C — Interface web hybride et contextuelle sur une page, avec synthèse et graphe centraux, panneaux secondaires ouverts à la demande. | SRC-C | REC-C-01, REC-C-02 |
| [C2](../CADRAGE/LOTS/C.md) | Option C — Saisie rapide et suivi dynamique, avec paramètres avancés repliables et suivi des opérations et consommations réellement constatées. | SRC-C | REC-C-03, REC-C-04, REC-C-05, REC-X-01 |
| [C3](../CADRAGE/LOTS/C.md) | Option C — Synthèse évolutive, structurée et interactive, reliée aux entités, relations et sources ; distinguant faits, hypothèses, contradictions et limites. | SRC-C | REC-C-06, REC-C-18, REC-X-03 |
| [C4](../CADRAGE/LOTS/C.md) | Option C — Graphe adaptatif, sémantique et exploratoire : modes réseau, arborescent et regroupé, filtres, exploration progressive et conventions de représentation des relations. | SRC-C | REC-C-07, REC-C-08, REC-C-09 |
| [C5](../CADRAGE/LOTS/C.md) | Option C — Fiches contextuelles enrichies et traçables, avec provenance au niveau des informations, sections détaillées et historique. | SRC-C | REC-C-10, REC-C-11 |
| [C6](../CADRAGE/LOTS/C.md) | Option C — Validation supervisée, non destructive et réversible ; distinction entre étayage documentaire et décision de l'utilisateur. | SRC-C | REC-C-12, REC-C-13, REC-C-14, REC-C-19 |
| [C7](../CADRAGE/LOTS/C.md) | Option C — Espace d'investigation unifié et navigation multi-branches, vues par branche et consolidée, rapports consultables et exports déclenchés manuellement. | SRC-C | REC-C-15, REC-C-16, REC-C-17, REC-C-18 |

## D

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [D1](../CADRAGE/LOTS/D.md) | Option C — Architecture locale structurée, versionnée et résiliente | SRC-D | REC-D1-01, REC-D1-02 |
| [D2](../CADRAGE/LOTS/D.md) | Option C — Configuration multi-fournisseurs IA avec orchestration supervisée | SRC-D | REC-D2-01, REC-D2-02, REC-D2-03 |
| [D3](../CADRAGE/LOTS/D.md) | Option C — Profils de recherche avec limites ajustables | SRC-D | REC-D3-01, REC-D3-02 |
| [D4](../CADRAGE/LOTS/D.md) | Option C — Conservation différenciée, cache intelligent et nettoyage supervisé | SRC-D | REC-D4-01, REC-D4-02 |
| [D5](../CADRAGE/LOTS/D.md) | Option C enrichie — Archives portables .osia, restitution HTML autonome interactive et restauration supervisée | SRC-D | REC-D5-01, REC-D5-02, REC-D5-03, REC-D5-04, REC-D5-05 |
| [D6](../CADRAGE/LOTS/D.md) | Option C — Confidentialité native et sécurité graduée | SRC-D | REC-D6-01, REC-D6-02 |
| [D7](../CADRAGE/LOTS/D.md) | Option C — Paramètres hiérarchisés et résilience supervisée | SRC-D | REC-D7-01, REC-D7-02, REC-D7-03 |

## T1

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [EXEC-01](../CADRAGE/LOTS/T1.md) | Moteur autonome, interfaces séparées | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-01 |
| [EXEC-02](../CADRAGE/LOTS/T1.md) | Installation Desktop ou Server | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-02 |
| [EXEC-03](../CADRAGE/LOTS/T1.md) | Distribution unifiée, frontend web facultatif | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-03 |
| [EXEC-04](../CADRAGE/LOTS/T1.md) | REST et événements SSE | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-04 |
| [EXEC-05](../CADRAGE/LOTS/T1.md) | Exposition et sécurité selon le mode | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-05 |
| [EXEC-06](../CADRAGE/LOTS/T1.md) | Mises à jour manuelles avec notification | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-06 |
| [EXEC-07](../CADRAGE/LOTS/T1.md) | Client GNOME ultérieur | SRC-T3 / SRC-T4T8 / CTX-T1 | AC-EXEC-07 |

## T2

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T2.1](../CADRAGE/LOTS/T2.md) | B — PostgreSQL comme base principale | SRC-T2 | AC-T2-01 |
| [T2.2](../CADRAGE/LOTS/T2.md) | C — Hybride avec déduplication : métadonnées en base, preuves et binaires dans un espace de fichiers dédié, empreintes SHA-256 | SRC-T2 | AC-T2-02 |
| [T2.3](../CADRAGE/LOTS/T2.md) | C — Organisation native Linux personnalisable, adaptée à Desktop/Server, données isolées | SRC-T2 | AC-T2-03 |
| [T2.4](../CADRAGE/LOTS/T2.md) | C — Protection complète : transactions, migrations, vérifications d'intégrité, reprise des interruptions et cohérence base/fichiers | SRC-T2 | AC-T2-04 |
| [T2.5](../CADRAGE/LOTS/T2.md) | C — Hybride : manuelle et automatique facultative, avec notifications, rétention et destination configurable | SRC-T2 | AC-T2-05 |
| [T2.6](../CADRAGE/LOTS/T2.md) | B — Sauvegarde cohérente à chaud, sans arrêt complet du moteur, manifeste et vérification | SRC-T2 | AC-T2-06 |
| [T2.7](../CADRAGE/LOTS/T2.md) | C — Sécurité graduée : permissions Linux, compatibilité chiffrement système et chiffrement applicatif facultatif | SRC-T2 | AC-T2-07 |
| [T2.8](../CADRAGE/LOTS/T2.md) | C — Gestion intelligente : statistiques, seuils, quotas et nettoyage supervisé des données techniques purgeables | SRC-T2 | AC-T2-08 |

## T3

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T3.1](../CADRAGE/LOTS/T3.md) | Option A — Python comme langage principal du moteur | SRC-T3 | AC-T3-01 |
| [T3.2](../CADRAGE/LOTS/T3.md) | Option C — Monolithe modulaire évolutif | SRC-T3 | AC-T3-02 |
| [T3.3](../CADRAGE/LOTS/T3.md) | Option C — Moteur autonome avec points d'entrée CLI, API, service et internes | SRC-T3 | AC-T3-03 |
| [T3.4](../CADRAGE/LOTS/T3.md) | Option C — Orchestrateur d'investigation dynamique supervisé | SRC-T3 | AC-T3-04 |
| [T3.5](../CADRAGE/LOTS/T3.md) | Option C — Modèle hybride asynchrone et multiprocessus | SRC-T3 | AC-T3-05 |
| [T3.6](../CADRAGE/LOTS/T3.md) | Option C — État persistant avec journal d'exécution et reprise contrôlée | SRC-T3 | AC-T3-06 |
| [T3.7](../CADRAGE/LOTS/T3.md) | Option C — Contrats d'échange typés, versionnés et découplés | SRC-T3 | AC-T3-07 |
| [T3.8](../CADRAGE/LOTS/T3.md) | Option C — Extensions déclaratives avec isolation graduée | SRC-T3 | AC-T3-08 |
| [T3.9](../CADRAGE/LOTS/T3.md) | Option C — Courtier IA centralisé avec adaptateurs fournisseurs | SRC-T3 | AC-T3-09 |
| [T3.10](../CADRAGE/LOTS/T3.md) | Option C — Chaîne de traitement séparée avec provenance et validation | SRC-T3 | AC-T3-10 |
| [T3.11](../CADRAGE/LOTS/T3.md) | Option C — Moteur de politiques indépendant et autorisations transactionnelles | SRC-T3 | AC-T3-11 |
| [T3.12](../CADRAGE/LOTS/T3.md) | Option C — Gestion contextuelle des erreurs et des interruptions | SRC-T3 | AC-T3-12 |
| [T3.13](../CADRAGE/LOTS/T3.md) | Option B — Journalisation structurée, observabilité avancée différée | SRC-T3 | AC-T3-13 |
| [T3.14](../CADRAGE/LOTS/T3.md) | Option C — Tests multicouches incluant simulations d'investigations | SRC-T3 | AC-T3-14 |

## T4

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T4.1](../CADRAGE/LOTS/T4.md) | le moteur élabore un plan initial à partir de l'objectif utilisateur, puis peut le réviser au fil des découvertes. | SRC-T4T8 | AC-T4-01 |
| [T4.2](../CADRAGE/LOTS/T4.md) | les tâches et leur coordination reposent sur un ordonnanceur persistant utilisant PostgreSQL. | SRC-T4T8 | AC-T4-02 |
| [T4.3](../CADRAGE/LOTS/T4.md) | chaque investigation définit des limites et des branches liées, mais identifiables séparément. | SRC-T4T8 | AC-T4-03 |
| [T4.4](../CADRAGE/LOTS/T4.md) | les tâches indépendantes peuvent s'exécuter en parallèle, dans des limites configurables. | SRC-T4T8 | AC-T4-04 |
| [T4.5](../CADRAGE/LOTS/T4.md) | ordonner les pistes selon leur utilité attendue, sous supervision du moteur. | SRC-T4T8 | AC-T4-05 |
| [T4.6](../CADRAGE/LOTS/T4.md) | l'investigation s'arrête lorsque les conditions pertinentes sont atteintes. | SRC-T4T8 | AC-T4-06 |
| [T4.7](../CADRAGE/LOTS/T4.md) | journal d'exécution et état persistant permettent la reprise maîtrisée. | SRC-T4T8 | AC-T4-07 |
| [T4.8](../CADRAGE/LOTS/T4.md) | des garde-fous techniques empêchent les boucles de recherche et l'explosion des coûts ou ressources. | SRC-T4T8 | AC-T4-08 |
| [T4.9](../CADRAGE/LOTS/T4.md) | exposer l'état et les événements de recherche à l'interface. | SRC-T4T8 | AC-T4-09 |

## T5

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T5.1](../CADRAGE/LOTS/T5.md) | classer les connecteurs selon leur niveau de confiance : officiels, tiers approuvés, expérimentaux. | SRC-T4T8 | AC-T5-01 |
| [T5.2](../CADRAGE/LOTS/T5.md) | associer isolation par processus et protections Linux graduées. | SRC-T4T8 | AC-T5-02 |
| [T5.3](../CADRAGE/LOTS/T5.md) | recourir à Playwright lorsque les API ou accès HTTP classiques ne suffisent pas. | SRC-T4T8 | AC-T5-03 |
| [T5.4](../CADRAGE/LOTS/T5.md) | contrôler les connexions sortantes indépendamment des connecteurs. | SRC-T4T8 | AC-T5-04 |
| [T5.5](../CADRAGE/LOTS/T5.md) | secrets non persistés par défaut ; coffre chiffré facultatif. | SRC-T4T8 | AC-T5-05 |
| [T5.6](../CADRAGE/LOTS/T5.md) | traiter tous les résultats de collecte comme des données, jamais comme des ordres de pilotage. | SRC-T4T8 | AC-T5-06 |
| [T5.7](../CADRAGE/LOTS/T5.md) | protections adaptées au mode d'installation. | SRC-T4T8 | AC-T5-07 |
| [T5.8](../CADRAGE/LOTS/T5.md) | une couche de politiques vérifie les conditions d'accès, restrictions techniques, autorisations, catégories de données et règles de conservation. | SRC-T4T8 | AC-T5-08 |
| [T5.9](../CADRAGE/LOTS/T5.md) | conserver un audit de sécurité séparé de la télémétrie technique générale. | SRC-T4T8 | AC-T5-09 |

## T6

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T6.1](../CADRAGE/LOTS/T6.md) | le référentiel de graphe repose sur PostgreSQL, sans base graphe spécialisée obligatoire en V1. | SRC-T4T8 | AC-T6-01 |
| [T6.2](../CADRAGE/LOTS/T6.md) | utiliser un modèle d'entités versionnable, extensible et doté d'identifiants internes stables. | SRC-T4T8 | AC-T6-02 |
| [T6.3](../CADRAGE/LOTS/T6.md) | chaque relation possède un type, les entités concernées, une éventuelle direction, une période, des justificatifs, un niveau d'étayage et un statut de validation. | SRC-T4T8 | AC-T6-03 |
| [T6.4](../CADRAGE/LOTS/T6.md) | rapprocher progressivement sur la base d'identifiants, normalisations, similarités et recoupements ; l'IA peut proposer des correspondances. | SRC-T4T8 | AC-T6-04 |
| [T6.5](../CADRAGE/LOTS/T6.md) | les rapprochements significatifs sont soumis à validation humaine quand l'identité est ambiguë. | SRC-T4T8 | AC-T6-05 |
| [T6.6](../CADRAGE/LOTS/T6.md) | conserver les affirmations concurrentes, sans effacement arbitraire. | SRC-T4T8 | AC-T6-06 |
| [T6.7](../CADRAGE/LOTS/T6.md) | ne pas réduire la fiabilité à un score unique opaque. | SRC-T4T8 | AC-T6-07 |
| [T6.8](../CADRAGE/LOTS/T6.md) | partager un référentiel d'entités et relations entre investigations/branches, tout en préservant objectifs, observations, interprétations et décisions propres à chaque contexte. | SRC-T4T8 | AC-T6-08 |
| [T6.9](../CADRAGE/LOTS/T6.md) | indexer et charger progressivement le graphe. | SRC-T4T8 | AC-T6-09 |

## T7

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T7.1](../CADRAGE/LOTS/T7.md) | les archives d'investigation utilisent un conteneur documenté, indépendant de l'installation d'origine. | SRC-T4T8 | AC-T7-01 |
| [T7.2](../CADRAGE/LOTS/T7.md) | détecter corruption, absence ou altération des contenus. | SRC-T4T8 | AC-T7-02 |
| [T7.3](../CADRAGE/LOTS/T7.md) | autoriser archives chiffrées ou non, avec protection globale des contenus et métadonnées sensibles lorsque le chiffrement est choisi. | SRC-T4T8 | AC-T7-03 |
| [T7.4](../CADRAGE/LOTS/T7.md) | permettre l'export d'une investigation, de certaines branches, ou d'un sous-ensemble choisi de preuves/données. | SRC-T4T8 | AC-T7-04 |
| [T7.5](../CADRAGE/LOTS/T7.md) | générer un rapport consultable hors ligne, sans OSIA ni serveur. | SRC-T4T8 | AC-T7-05 |
| [T7.6](../CADRAGE/LOTS/T7.md) | les imports sont contrôlés avant modification des données existantes. | SRC-T4T8 | AC-T7-06 |
| [T7.7](../CADRAGE/LOTS/T7.md) | versionner les schémas d'archives et gérer explicitement leur évolution. | SRC-T4T8 | AC-T7-07 |
| [T7.8](../CADRAGE/LOTS/T7.md) | conserver les caractéristiques essentielles de chaque export, sans exposer ses secrets. | SRC-T4T8 | AC-T7-08 |
| [T7.9](../CADRAGE/LOTS/T7.md) | séparer rigoureusement : | SRC-T4T8 | AC-T7-09 |

## T8

| Identifiant | Décision / portée | Source | Contrôles associés |
| --- | --- | --- | --- |
| [T8.1](../CADRAGE/LOTS/T8.md) | tous les appels à des modèles passent par le courtier IA du moteur. | SRC-T4T8 | AC-T8-01 |
| [T8.2](../CADRAGE/LOTS/T8.md) | distinguer les responsabilités de planification, sélection, extraction, rapprochement, analyse et synthèse. | SRC-T4T8 | AC-T8-02 |
| [T8.3](../CADRAGE/LOTS/T8.md) | sélectionner les modèles selon type de tâche, qualité nécessaire, coût, disponibilité, préférences, confidentialité et budget. | SRC-T4T8 | AC-T8-03 |
| [T8.4](../CADRAGE/LOTS/T8.md) | encadrer les appels payants aux niveaux global, investigation, branche, fournisseur, modèle et opération. | SRC-T4T8 | AC-T8-04 |
| [T8.5](../CADRAGE/LOTS/T8.md) | minimiser les coûts inutiles. | SRC-T4T8 | AC-T8-05 |
| [T8.6](../CADRAGE/LOTS/T8.md) | les réponses utilisées par le moteur doivent respecter des contrats de données versionnés. | SRC-T4T8 | AC-T8-06 |
| [T8.7](../CADRAGE/LOTS/T8.md) | une affirmation exploitable doit être reliée aux données ou sources qui l'étayent. | SRC-T4T8 | AC-T8-07 |
| [T8.8](../CADRAGE/LOTS/T8.md) | contrôler explicitement quelles données quittent l'installation et vers quels fournisseurs. | SRC-T4T8 | AC-T8-08 |
| [T8.9](../CADRAGE/LOTS/T8.md) | permettre tentatives limitées, délais d'attente, identification d'indisponibilités, alternatives et poursuite partielle sans IA lorsque possible. | SRC-T4T8 | AC-T8-09 |
| [T8.10](../CADRAGE/LOTS/T8.md) | mesurer l'efficacité des modèles par tâche. | SRC-T4T8 | AC-T8-10 |

## Règles détaillées et invariants

Les 96 règles C1-01…C7-20 sont conservées dans le lot C ; leurs scénarios se répartissent par arbitrage ci-dessus. Les 13 thèmes A.1–A.13 complètent les 12 arbitrages A1–A12 : ces nomenclatures ne sont pas interchangeables. Les dix invariants du lot D sont nommés D-INV-01…10 dans cette édition pour éviter une collision avec les anciens invariants techniques.
Les règles transversales OSIA-I-01…16 de [TECHNIQUE.md](../CADRAGE/TECHNIQUE.md) renvoient aux décisions d’origine. Les clarifications COH-* du rapport d’audit expliquent les harmonisations, sans se présenter comme de nouveaux arbitrages.

## Évolutions ultérieures

Toute évolution doit distinguer : correction éditoriale, choix de conception compatible, changement d’arbitrage produit. Consigner le motif, les décisions concernées, l’autorité et la date, les documents modifiés et les critères de recette affectés. Ne pas effacer la trace d’une décision remplacée ; retirer sa formulation devenue obsolète des instructions actives.

## Suivi de clôture — vérification ciblée du 07/11/2026 (commit `7ec5ea3`, issue #17)

La vérification de clôture confirme la clôture du suivi des PR (CI verte sur `main`, 257 tests) et corrige l’affirmation « seul Playwright reste à arbitrer ». Traitements actés :

| Référence | Traitement | Où |
| --- | --- | --- |
| EXEC-03 (frontend facultatif) | **Livré** : choix d'activation réel — `web_ui_enabled` / `OSIA_WEB_UI_ENABLED` / `osia serve --no-web-ui` / `create_app(web_ui=False)` ; mode API seul testé (aucune route web, auth serveur conservée) | `src/osia/config.py`, `src/osia/api/app.py`, `src/osia/cli.py`, `tests/test_audit_cloture.py`, CONCEPTION/01 §1 |
| EXEC-06 (notification de version) | **Livré** : check best-effort au démarrage du serveur via le NetworkGuard + `osia version --check` + `GET /api/v1/system/version` ; mises à jour toujours manuelles, aucune mise à jour automatique | `src/osia/version.py`, `src/osia/server.py`, `src/osia/api/app.py`, `src/osia/cli.py`, `tests/test_audit_cloture.py` |
| V1.2 / B-ACC-04 / AC-T5-03 (Playwright) | **Décision ouverte soumise au porteur** : report en V2 à acter explicitement, puis à répercuter dans PERIMETRE-V1 et la matrice de recette (issue de suivi dédiée) | COWORKAI/RECETTE-APPLICATIVE.md §8 |
| Qualification externe BODACC/GLEIF | Reste à réaliser hors CI (aucun appel réel effectué) | COWORKAI/RECETTE-APPLICATIVE.md §8 |

## Décision porteur complémentaire — 09/11/2026 — écran « Paramètres » dans l'interface web

Lors de l'installation (09/11/2026), le porteur a réaffirmé une exigence exprimée dans la conversation de cadrage initiale mais non reprise dans le lot C consolidé : pouvoir **configurer l'instance depuis l'interface web**. Changement de périmètre acté par le porteur ; la divergence avec `CADRAGE/LOTS/C.md` (qui laissait « paramètres globaux » et « clés/API » à D/T2/T7, avec une surface CLI/API prescrite par CON-11 et CON-13) est exposée ici, pas absorbée silencieusement.

- **Livré** : vue `#/parametres` (`src/osia/web/`) adossée aux API existantes — fournisseurs IA (liste `GET /api/v1/ai/providers`, test de connexion non facturé `POST /api/v1/ai/test`, autorisation de repli local→cloud `POST /api/v1/ai/fallback`), paramètres globaux (`GET/PUT /api/v1/settings`), profils (`GET/POST /api/v1/profiles`), connecteurs (`GET /api/v1/connectors`, `POST .../toggle` avec confirmation explicite pour un connecteur expérimental, T5.1), noms des secrets (`GET /api/v1/secrets`).
- **Contrainte conservée** : aucune clé ou valeur de secret n'est saisie, affichée ou transmise par le navigateur (D2 §4.3, T5.5, OSIA-I-12) — le coffre reste géré en CLI (`osia secrets list|set|delete`).
- **Vérification** : `tests/test_web.py::test_web_settings_view_wired_to_existing_api` + tests API existants (`test_con06.py`, `test_con11.py`, `test_con13.py`) + smoke Node `test_app_js_smoke_node`.

### Complément demandé par le porteur — configuration des connexions IA

La restriction de saisie ci-dessus est levée pour les **clés de fournisseurs IA**. Le formulaire transmet la clé masquée au backend OSIA pour la connexion ou le test explicite. Le backend ne renvoie jamais sa valeur, ne la stocke pas dans le navigateur ou la base et la conserve en mémoire du service. Le coffre CLI reste disponible séparément.

Le parcours couvre Mistral, une API locale et une API cloud compatible OpenAI. La sélection explicite affecte un modèle aux rôles existants de planification, extraction et synthèse. Les autorisations de dépense, plafonds et règles de repli du courtier continuent de s’appliquer (D2, T5.5, T8.4, T8.8 et T8.9).
