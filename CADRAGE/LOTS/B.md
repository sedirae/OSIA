# OSIA — Cadrage fonctionnel — Lot B : Sources et connecteurs

> **Édition consolidée : 1.1 — 06/11/2026.** Les arbitrages conservent leur validation initiale. Cette édition harmonise les formulations avec les lots ultérieurs ; elle ne vaut pas attestation de développement. Références : [index](../README.md), [résolutions de cohérence](../AUDIT-COHERENCE.md), [registre des décisions](../../COWORKAI/DECISIONS.md).


**Version :** 1.1  
**Date :** 5 novembre 2026  
**Statut :** cadrage fonctionnel validé — lot B clôturé  
**Périmètre :** catalogue des sources, méthodes d'accès, orchestration des connecteurs, qualification des informations, maîtrise des ressources et maintenance  
**Nature :** document de référence fonctionnel ; ne constitue ni une spécification technique exhaustive, ni une attestation d'implémentation.

---

## 1. Objet et références

Le lot B décrit la manière dont OSIA découvre, sélectionne, consulte, recoupe et maintient les sources exploitées dans ses investigations OSINT. Le système doit être généraliste, international et extensible, tout en donnant la priorité aux sources adaptées à la question posée.

Il complète le **lot A — Moteur d'investigation**, sans en modifier les décisions. En particulier :

- Les investigations suivent les limites de profondeur (niveaux de liaison jusqu'à 10 selon le réglage utilisateur) et les budgets explicitement définis au lot A.
- Le moteur peut découvrir des pistes annexes mais ne doit pas explorer indéfiniment toutes les ramifications.
- Selon l'arbitrage **A5**, lorsque la réponse à l'objectif est suffisamment étayée, l'investigation s'arrête automatiquement ; les pistes pertinentes restantes sont présentées à l'utilisateur sans être exécutées.
- Une prolongation nécessite une action explicite de l'utilisateur. Elle prend la forme d'une **nouvelle branche liée** à l'investigation initiale, réutilisant contexte et résultats, dotée de ses propres limites explicites de profondeur et de budget. Aucun dépassement de limite payante n'est autorisé sans nouvel accord.

Les modalités de présentation sont principalement du ressort du **lot C — Interface et restitution**. La configuration locale, la persistance et la gestion technique des paramètres et secrets relèvent principalement du **lot D — Paramètres et données locales**.

### 1.1 Principe directeur

> L'IA propose et interprète ; les composants de contrôle indépendants déterminent ce qui peut effectivement être exécuté, sous quelles conditions et dans quelles limites.

---

## 2. Registre des décisions validées

| ID | Domaine | Choix validé | Statut |
| --- | --- | --- | --- |
| **B1** | Architecture | **C — Architecture hybride** : connecteurs préintégrés sur un socle modulaire | **VALIDÉ** |
| **B2** | Catalogue | **C — Catalogue international évolutif**, généraliste, sans frontière géographique structurelle | **VALIDÉ** |
| **B3** | Accès | **C — Accès multimode adaptatif** : API, recherche web, extraction, documents et données ouvertes, navigateur avancé si justifié | **VALIDÉ** |
| **B4** | Orchestration | **C — Sélection hybride supervisée** : choix proposés par l'IA, exécution conditionnée par un contrôleur indépendant | **VALIDÉ** |
| **B5** | Fiabilité | **C — Fiabilité multidimensionnelle et explicable** : éléments de preuve et critères distincts | **VALIDÉ** |
| **B6** | Ressources | **C — Gestionnaire centralisé avec réservations** : suivi des coûts, quotas, appels simultanés et limites | **VALIDÉ** |
| **B7** | Maintenance | **C — Maintenance autonome supervisée** : détection, diagnostic, corrections encadrées, validation des changements sensibles | **VALIDÉ** |

Ces sept arbitrages sont définitifs au titre de la **v1.0 du lot B**. Les exemples de fournisseurs et les paramètres chiffrés non arbitrés restent des propositions ou des éléments à préciser.

---

## 3. B1 — Architecture hybride des connecteurs

### 3.1 Exigence fonctionnelle

OSIA doit offrir un **noyau de connecteurs disponibles dès la première version**, reposant sur une **architecture modulaire** pour permettre l'ajout de nouvelles sources sans modifier le cœur du moteur d'investigation.

Chaque connecteur doit pouvoir être configuré, activé, désactivé et surveillé indépendamment. Une panne ou la désactivation d'un connecteur ne doit pas provoquer l'arrêt automatique de l'ensemble d'OSIA.

### 3.2 Contrat fonctionnel commun

Un connecteur doit exposer, lorsque cela s'applique :

- son identifiant, sa version, son fournisseur et son périmètre géographique ou thématique ;
- les catégories de données et les types de recherches pris en charge ;
- ses méthodes d'accès autorisées et son mode d'authentification ;
- ses paramètres de requête, la nature de ses résultats et les métadonnées de provenance ;
- ses contraintes d'utilisation, quotas, coûts connus et état de disponibilité ;
- des capacités de test, de diagnostic et de normalisation des réponses.

Le contrat technique précis (interfaces, formats, SDK ou protocole de modules) sera fixé pendant la conception technique.

**Résultat attendu :** le moteur interroge des capacités normalisées de sources, sans dépendre d'une implémentation propre à chaque fournisseur.

---

## 4. B2 — Catalogue international évolutif

### 4.1 Périmètre

OSIA est conçu comme un **outil OSINT généraliste**, et non uniquement comme un moteur de recherche sur les sociétés. Il doit pouvoir croiser des informations sur les entreprises, organisations, lieux, ressources Internet, documents, événements et activités publiques, ainsi que les informations publiques sur des personnes lorsque leur traitement est légitime.

Les **sept familles fonctionnelles** du catalogue sont :

1. **Entreprises et organisations** : registres, établissements, dirigeants, mandats, activités, liens documentés.
2. **Web et moteurs de recherche** : découverte de sites, pages, actualités et index publics.
3. **Domaines et infrastructure Internet** : DNS, RDAP, certificats, adresses IP et technologies publiques.
4. **Documents et archives** : PDF publics, actes, rapports, anciennes versions de pages, publications.
5. **Géographie et adresses** : géocodage, cartographie, établissements, voisinage géographique.
6. **Personnes et activités publiques** : fonctions publiques/professionnelles déclarées, travaux publiés, profils accessibles légalement.
7. **Sources spécialisées** : justice, marchés publics, propriété intellectuelle, recherche scientifique et données sectorielles.

Ces familles sont **interconnectables** : une découverte provenant de l'une d'elles peut justifier l'interrogation d'une autre, sous le contrôle du lot A et de B4/B6.

### 4.2 Sources candidates (illustratives, non exhaustives)

| Famille | Sources ou services candidats |
| --- | --- |
| Entreprises françaises | API Recherche d'Entreprises, INSEE/Sirene, INPI/RNE, BODACC |
| Associations | Répertoire national des associations et registres publics pertinents |
| Entreprises internationales | GLEIF/LEI, Companies House et autres registres nationaux accessibles |
| Recherche web | API de recherche et moteurs dont l'accès automatisé est autorisé |
| Infrastructure | DNS, RDAP, transparence des certificats |
| Archives et connaissances | Internet Archive/Wayback Machine, Wikidata |
| Géographie | OpenStreetMap et services de géocodage |
| Publications | HAL, Crossref, OpenAlex |
| Développement public | Dépôts publics GitHub/GitLab |
| Sources spécialisées | INPI, Espacenet, BOAMP, TED, bases de jurisprudence accessibles |

**Précision :** cette table recense des **candidats à évaluer**, et non une obligation d'intégrer chaque service dès la V1. Leur disponibilité, leurs tarifs, leurs conditions contractuelles et les catégories de données réellement accessibles devront être vérifiés au moment de l'intégration.

### 4.3 Priorité de réalisation

Un premier socle opérationnel comportera des sources françaises et des sources internationales pertinentes, puis le catalogue sera élargi progressivement. Aucune dépendance de conception ne doit imposer une limitation permanente à la France ou à l'Europe.

---

## 5. B3 — Accès multimode adaptatif

### 5.1 Méthodes prises en charge

OSIA doit pouvoir choisir parmi :

| Mode | Fonction |
| --- | --- |
| API structurée | Interroger des données de référence et des services spécialisés |
| Recherche web | Découvrir des sources et ressources pertinentes |
| Extraction web standard | Lire HTML, métadonnées et liens de pages publiques autorisées |
| Analyse documentaire | Exploiter des PDF, actes et fichiers publics autorisés |
| Jeux de données ouverts | Consommer ou indexer des données CSV, JSON, XML et formats assimilés |
| Navigation/extraction avancée | Utiliser un navigateur automatisé exécutant JavaScript lorsque nécessaire et autorisé |

Le mode avancé est **facultatif au niveau de chaque opération**, non systématique. Son surcoût et son intérêt doivent être appréciés.

### 5.2 Principes de sélection

- Privilégier une **source primaire compétente pour le fait** recherché lorsque disponible.
- Employer la recherche web pour découvrir des pistes et des sources complémentaires.
- Ne pas transformer un extrait de moteur de recherche, à lui seul, en preuve complète lorsque la consultation de la source d'origine est nécessaire.
- Autoriser les voies de repli, à condition qu'elles soient permises et restent dans les limites.
- Conserver pour chaque élément sa source, sa méthode de collecte et sa temporalité.

L'ordre des méthodes est adaptatif : une investigation sur un domaine peut commencer par DNS/RDAP plutôt que par un registre d'entreprises.

### 5.3 Restrictions

OSIA ne doit pas contourner les authentifications, CAPTCHA, restrictions d'accès ou autres protections techniques applicables. Les méthodes admises doivent être décrites dans la fiche du connecteur. L'accessibilité publique d'une information ne suffit pas à autoriser toute forme d'extraction, de conservation ou de réutilisation.

---

## 6. B4 — Sélection dynamique supervisée des sources

### 6.1 Séparation des responsabilités

**L'IA** évalue l'objectif en cours, les données déjà obtenues et les pistes nouvelles ; elle propose des actions pertinentes, en indiquant leur justification.

**Le contrôleur indépendant** vérifie avant exécution :

- les méthodes et autorisations d'accès ;
- la cohérence avec l'objectif et la profondeur courante ;
- le budget restant et les ressources réservées ;
- les doublons et résultats réutilisables ;
- les quotas, disponibilités et contraintes du fournisseur.

L'IA ne peut ni modifier ses propres plafonds ni contourner un refus par une autre méthode d'accès interdite.

### 6.2 Priorisation

Les actions candidates sont évaluées selon la **pertinence**, la **fiabilité attendue de la source pour le fait**, le **coût**, la **disponibilité**, la **fraîcheur nécessaire** et le **potentiel d'information nouvelle**.

Les conditions d'accès et les plafonds sont des **contraintes bloquantes**, pas des critères qu'un bon score de pertinence pourrait compenser.

### 6.3 Économie d'exploration

- Dédupliquer les recherches équivalentes.
- Réutiliser les résultats précédemment recueillis lorsque leur validité le permet.
- Réévaluer les pistes après chaque résultat pertinent.
- Écarter les branches devenues inutiles à l'objectif.
- Soumettre les recherches parallèles à une réservation préalable de ressources.

### 6.4 Arrêt et prolongation

Lorsque l'objectif est suffisamment étayé, OSIA **s'arrête**, même si la profondeur maximale n'a pas été atteinte. Il présente les pistes restantes pertinentes, puis laisse à l'utilisateur l'initiative de poursuivre, conformément à **A5**. Aucune piste restante ne déclenche de consommation supplémentaire sans cette action explicite.

---

## 7. B5 — Croisement, normalisation et fiabilité

### 7.1 Normalisation des résultats

Les résultats hétérogènes sont transformés en représentations communes d'**entités**, de **relations**, de **faits**, de **documents** et de **sources**. Les valeurs originales sont conservées afin de rendre les transformations vérifiables.

Exemples : société/raison sociale → organisation ; SIREN ou LEI → identifiant ; établissement → entité et adresse associée ; mandat de dirigeant → relation datée entre personne et organisation.

### 7.2 Réconciliation d'entités

OSIA distingue au minimum :

1. **Concordance fortement étayée** : identifiant officiel commun et pertinent.
2. **Correspondance probable** : plusieurs attributs convergents à vérifier.
3. **Similarité ou indice** : même nom, même adresse ou caractéristique isolée, sans fusion automatique.

Une homonymie ne suffit jamais à fusionner deux personnes. Une adresse commune ne suffit pas à démontrer une affiliation entre entreprises.

### 7.3 Statut des informations

Le système distingue les **faits directement documentés**, **indices**, **hypothèses** et **contradictions**. Ces natures ne doivent pas être confondues avec une mesure unique de confiance.

Par exemple, une adresse commune et un code NAF identique peuvent justifier la recherche d'un dirigeant commun, sans établir une participation capitalistique.

### 7.4 Provenance et preuve

Chaque affirmation exploitée dans une conclusion doit être reliée à ses éléments de preuve. Conserver, selon disponibilité et droits :

- l'organisme ou service d'origine ;
- l'URL, l'identifiant d'enregistrement ou la référence documentaire ;
- l'information originale / l'extrait pertinent ;
- la date de validité ou de publication, si connue ;
- la date de consultation ;
- la méthode d'obtention ;
- l'interprétation et son éventuelle part de déduction ;
- les vérifications réalisées et contradictions restantes.

Une empreinte de contenu ou une référence de version peut être ajoutée lorsqu'elle est pertinente et autorisée ; elle ne suppose pas nécessairement la conservation intégrale du contenu.

### 7.5 Fiabilité multidimensionnelle

La qualité est évaluée selon plusieurs dimensions explicites :

| Dimension | Question directrice |
| --- | --- |
| Autorité | La source est-elle compétente pour le fait considéré ? |
| Directivité | Décrit-elle directement le fait ou relaie-t-elle une autre source ? |
| Indépendance | Les corroborations sont-elles réellement indépendantes ? |
| Identité | La bonne entité a-t-elle été identifiée ? |
| Temporalité | Les faits correspondent-ils à la période recherchée ? |
| Cohérence | Les contradictions ont-elles été expliquées ou sont-elles ouvertes ? |

OSIA fournit un **statut explicable de synthèse** et peut employer des scores internes de priorisation ou de rapprochement ; ces scores ne doivent pas être présentés comme des probabilités certaines non calibrées.

Une contradiction apparente peut résulter de périodes différentes. Une information ancienne peut rester historiquement correcte. L'absence de résultat n'est pas, en elle-même, une preuve d'inexistence.

---

## 8. B6 — Gestion centralisée des clés, quotas et coûts

### 8.1 Catégories de limites

OSIA distingue :

1. **Financières** : montant maximal de dépenses autorisées.
2. **Consommation** : tokens, appels, pages, traitements, téléchargements.
3. **Fournisseurs** : quotas, limites de débit et de concurrence.
4. **Techniques** : temps, mémoire, volume et exécution parallèle.

Les limites d'investigation du lot A s'appliquent en plus de ces contraintes.

### 8.2 Gestionnaire centralisé

Un composant indépendant du modèle et des connecteurs supervise :

- le **budget global** d'OSIA ;
- le **budget propre à chaque investigation** ;
- les **réservations par opération** avant le démarrage ;
- les limites spécifiques aux fournisseurs ;
- la comptabilisation des coûts réellement observés ;
- les annulations, rejets et reprises sur erreur ;
- l'historique des consommations, notamment des opérations de maintenance.

Lors d'appels concurrents, les réservations doivent être **atomiques** pour empêcher une double utilisation du budget disponible.

### 8.3 Respect effectif des plafonds

Une estimation de coût ne garantit pas la facture finale d'un fournisseur. En conséquence :

- OSIA doit privilégier des opérations dont la **consommation maximale peut être bornée**, et appliquer les plafonds natifs du fournisseur lorsqu'ils existent.
- Une opération payante dont l'exposition financière ne peut pas être suffisamment bornée doit être **refusée**, ou attendre une autorisation explicite correspondant à ce risque.
- Aucun dépassement autorisé implicitement n'est permis ; l'IA ne peut augmenter ni contourner les limites.
- Les coûts de surveillance et de maintenance doivent également être soumis à des limites dédiées et à la limite globale.

### 8.4 Clés et configurations

Chaque connecteur possède des paramètres d'authentification distincts (clé API, OAuth ou mécanisme applicable), une capacité de test de connexion et un état d'activation. Les secrets ne doivent être exposés ni à l'IA, ni à l'interface publique, ni aux journaux. Leur stockage concret relève du lot D.

### 8.5 Erreurs et indisponibilités

| Événement | Comportement attendu |
| --- | --- |
| Indisponibilité transitoire | Réessais limités et progressifs |
| Quota ou débit dépassé | Respect du délai de reprise communiqué, s'il existe |
| Clé invalide | Blocage des appels du connecteur concerné et signalement |
| Erreurs répétées | Mise en retrait temporaire du connecteur / circuit ouvert |
| Source inaccessible | Recherche d'une alternative autorisée et utile |
| Budget épuisé | Arrêt des opérations payantes concernées, restitution des résultats partiels |
| Coût non bornable | Non-exécution automatique de l'appel payant |

Une enquête interrompue doit pouvoir reprendre en réutilisant ses résultats et son contexte, après validation explicite de nouvelles limites lorsque cela est nécessaire ; la reprise ne crée pas de consommation rétroactive ni de nouvelle dépense implicite.

---

## 9. B7 — Actualisation, conformité et maintenance supervisée

### 9.1 Surveillance des connecteurs

OSIA vérifie la disponibilité, l'authentification, la structure et la cohérence des réponses, les performances, les quotas connus et les évolutions des conditions d'accès.

Une réponse HTTP techniquement valide ne suffit pas à prouver la validité fonctionnelle du connecteur : les champs attendus et les données doivent également être contrôlés.

États fonctionnels proposés :

- **Opérationnel** : contrôles satisfaisants.
- **Dégradé** : certaines fonctions restent utilisables, les autres sont exclues.
- **Suspendu** : anomalie critique, restriction ou doute bloquant.
- **Obsolète** : évolution ou remplacement exigeant adaptation.

Les libellés et présentations exacts pourront être précisés au lot C.

### 9.2 Actualisation des données

Distinguer la **mise à jour du connecteur** de la **revalidation des informations collectées**. La durée d'utilisation du cache dépend de la nature des données, de la question et des conditions d'utilisation. Une information historique ne doit pas être remplacée sans préserver sa période de validité.

Lorsque les mécanismes des sources le permettent, la revalidation conditionnelle peut limiter les transferts inutiles. Le cache et les snapshots doivent respecter les droits de conservation et de réutilisation des données.

### 9.3 Maintenance autonome supervisée

Séquence souhaitée : **détection → diagnostic → proposition d'adaptation → tests isolés → activation contrôlée → traçabilité / retour arrière**.

- OSIA peut identifier automatiquement les problèmes et préparer des corrections.
- Les changements **simples, préautorisés, couverts par des tests et sans modification sensible** peuvent être appliqués automatiquement.
- Une modification de **code exécutable, droits d'accès, permissions, politique d'accès ou tarification** nécessite une **validation humaine explicite avant activation en production**.
- Les modifications doivent être versionnées, auditables et réversibles lorsque cela est techniquement possible.
- Un connecteur incertain peut être retiré temporairement des recherches, sans arrêter les autres sources.

Cette autonomie concerne la **maintenance des connecteurs** ; elle n'accorde pas au moteur d'investigation un droit supplémentaire de contourner les limites du lot A ou de B6.

### 9.4 Conformité des accès

Chaque connecteur doit comporter une fiche documentant, selon les informations vérifiables : périmètre, types de données, méthodes d'accès admises, authentification, quotas, tarifs, conditions de collecte, conservation, réutilisation et redistribution, ainsi que la date de vérification de ces informations.

La présence de données sur une page publique ne rend pas automatiquement tous les traitements licites. Les obligations de protection des données personnelles, les conditions des fournisseurs et les restrictions techniques pertinentes s'appliquent. En cas de changement ou de doute sur un droit d'accès, les opérations concernées doivent être **suspendues jusqu'à vérification** ; l'IA n'est pas autorisée à écarter elle-même cette restriction.

### 9.5 Coût de la maintenance

Les sondes et vérifications doivent être proportionnées. Leur fréquence est configurable selon la source ; les contrôles légers sont préférés aux recherches complètes lorsque cela suffit. Les vérifications payantes sont budgétées par le gestionnaire B6.

---

## 10. Parcours fonctionnel de référence

**Cas illustratif :** « Existe-t-il une relation documentée entre l'entreprise A et l'entreprise B ? »

1. L'utilisateur définit l'objectif et ses limites conformément au lot A.
2. L'IA examine les capacités du catalogue (B1–B2) et propose les sources pertinentes (B4).
3. Le contrôleur vérifie droits d'accès, quotas, profondeur, budget et doublons (B3–B4–B6).
4. OSIA interroge les sources autorisées et normalise les résultats (B3–B5).
5. Une adresse identique constitue un **indice** ; un mandat commun documenté peut constituer une **relation établie pour une période donnée**. Les liens capitalistiques restent distincts et nécessitent des preuves propres (B5).
6. Le moteur réévalue les pistes en évitant les appels redondants (B4).
7. Dès que l'objectif est suffisamment étayé, il s'arrête et restitue les conclusions sourcées, leurs limites et les pistes restantes non explorées (A5, B5).
8. L'utilisateur peut, s'il le souhaite, autoriser une nouvelle branche avec ses propres limites (A5).

**Principe :** l'existence de nouvelles pistes n'autorise pas, à elle seule, leur exploration après l'arrêt de l'objectif principal.

---

## 11. Critères d'acceptation fonctionnels (dérivés des décisions)

Les critères suivants servent de base aux tests de conception et de recette ; ils ne présument d'aucune implémentation existante.

| ID | Critère vérifiable |
| --- | --- |
| B-ACC-01 | Un connecteur peut être désactivé sans bloquer les autres. |
| B-ACC-02 | Un connecteur ajouté via le contrat commun est exploitable sans modifier la logique métier centrale. |
| B-ACC-03 | Une recherche peut mobiliser plusieurs familles de sources et plusieurs modes autorisés. |
| B-ACC-04 | Un navigateur avancé n'est invoqué que si son usage est justifié, permis et budgété. |
| B-ACC-05 | L'IA ne peut lancer directement un appel refusé par le contrôleur indépendant. |
| B-ACC-06 | Une requête équivalente déjà satisfaite peut réutiliser un résultat valide plutôt que générer un nouvel appel. |
| B-ACC-07 | Une simple adresse commune n'est jamais étiquetée automatiquement « affiliation démontrée ». |
| B-ACC-08 | Une conclusion affichée peut être reliée aux éléments sources et à leur période de validité. |
| B-ACC-09 | Deux versions historiques compatibles d'une information ne sont pas nécessairement considérées contradictoires. |
| B-ACC-10 | Deux opérations simultanées ne peuvent réserver la même portion de budget disponible. |
| B-ACC-11 | Une opération payante dont le risque de dépassement n'est pas maîtrisé n'est pas exécutée automatiquement. |
| B-ACC-12 | Une API défaillante est isolée et peut être remplacée par une alternative autorisée. |
| B-ACC-13 | Une correction sensible de connecteur ne peut être activée en production sans validation explicite. |
| B-ACC-14 | Les vérifications périodiques sont soumises à des plafonds de ressources. |
| B-ACC-15 | Lorsque l'objectif est suffisamment étayé, OSIA s'arrête et laisse les autres pistes à l'état de propositions. |
| B-ACC-16 | Une prolongation autorisée reprend le contexte sous une nouvelle branche, avec nouveaux plafonds explicites. |

---

## 12. Articulation avec les décisions ultérieures

Les principes initialement renvoyés aux lots C et D sont désormais validés : interface et preuves (C), conservation et secrets (D), backend et contrats (T3), sécurité et Playwright (T5), graphe PostgreSQL (T6), archives (T7), courtier et budgets (T8).

Restent à spécifier, sans rouvrir B1–B7 : contrat logiciel exact et versions ; liste des connecteurs V1 ; fournisseurs de recherche web ; contrôles sémantiques par source ; borne de coût par fournisseur ; fréquences et environnement des tests de maintenance ; vérification des conditions d'accès et de réutilisation pour chaque intégration. Le calendrier de maintenance avancée relève du périmètre de livraison.

Les modèles de stockage et d'identifiants sont détaillés dans le cadre PostgreSQL et du graphe commun déjà retenu. Les modalités visuelles restent à concevoir dans le respect de C. Voir [conception restante](../CONCEPTION-RESTANTE.md).

---

## 13. Clôture du lot B et articulation avec la suite

**Lot B : clôturé en v1.0 ; sept arbitrages sur sept validés.**

Cette version définit les attentes fonctionnelles. Elle ne garantit pas qu'un fournisseur restera accessible, gratuit ou compatible, et elle ne déclenche aucune création de code, aucun appel API payant ni aucune modification de dépôt.

Les lots C, D et T1–T8 sont également clôturés. La suite est la conception détaillée, la définition exacte de la V1 et le phasage du développement.

En cas de conflit avec le lot A, vérifier les arbitrages déjà validés avant toute modification. Les évolutions ultérieures seront documentées par une nouvelle version, en distinguant explicitement **décision validée**, **proposition** et **point ouvert**.
