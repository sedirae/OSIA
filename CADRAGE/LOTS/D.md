# OSIA — Cadrage fonctionnel — Lot D : Paramètres et données locales

> **Édition consolidée : 1.1 — 06/11/2026.** Les arbitrages conservent leur validation initiale. Cette édition harmonise les formulations avec les lots ultérieurs ; elle ne vaut pas attestation de développement. Références : [index](../README.md), [résolutions de cohérence](../AUDIT-COHERENCE.md), [registre des décisions](../../COWORKAI/DECISIONS.md).


> **Version :** 1.1  
> **Date de validation :** 5 novembre 2026  
> **Statut :** VALIDÉ — Lot clôturé (D1 à D7)  
> **Projet :** OSIA — Application d'investigation OSINT assistée par IA  
> **Nature :** référentiel de décisions fonctionnelles ; les choix d'implémentation restant ouverts sont signalés comme tels.

## 1. Objet et portée

Ce document consolide les sept arbitrages validés du **lot D — Paramètres et données locales**. Il définit les exigences relatives au stockage local, à la configuration des fournisseurs IA, aux profils de recherche, à la conservation et au cache, aux sauvegardes et restitutions portables, à la confidentialité et à la résilience.

Il constitue une **référence de cadrage** pour la conception technique et le développement d'OSIA. Il n'a pas vocation à remplacer les référentiels des autres lots ni à figer une bibliothèque, un format interne ou une interface détaillée lorsqu'ils n'ont pas été arbitrés.

### 1.1. Dépendances avec les lots A, B et C

Les dispositions de ce lot s'inscrivent dans les principes déjà retenus :

- **Lot A — Investigation :** profondeur réglable de **1 à 10 rebonds relationnels** ; arrêt lorsque l'objectif est suffisamment étayé ; pistes supplémentaires proposées mais lancées **seulement après validation explicite**, comme nouvelles branches liées à l'investigation initiale avec paramètres et budgets propres.
- **Lot B — Sources et connecteurs :** catalogue et accès multi-sources ; sélection encadrée par un **moteur de règles indépendant de l'IA** ; gestionnaire centralisé des budgets, autorisations et réservations avant tout appel payant ; fournisseurs et connecteurs modulaires.
- **Lot C — Interface et restitution :** conservation des sources originales et des décisions humaines ; distinction entre étayage factuel et validation humaine ; graphe d'entités et arbre des investigations distincts ; branches et vue consolidée ; contradictions visibles ; restitution et réévaluation des conclusions dépendantes à partir des données déjà disponibles, sans provoquer d'appel payant non autorisé.

**Règle de priorité :** le lot D définit la configuration et la persistance de ces fonctions, sans modifier les garanties et décisions déjà validées dans A, B ou C.

## 2. Registre des arbitrages validés

| Réf. | Décision retenue | Statut |
|---|---|---|
| **D1** | Option C — Architecture locale structurée, versionnée et résiliente | Validé |
| **D2** | Option C — Configuration multi-fournisseurs IA avec orchestration supervisée | Validé |
| **D3** | Option C — Profils de recherche avec limites ajustables | Validé |
| **D4** | Option C — Conservation différenciée, cache intelligent et nettoyage supervisé | Validé |
| **D5** | **Option C enrichie** — Archives portables `.osia`, restitution HTML autonome interactive et restauration supervisée | Validé |
| **D6** | Option C — Confidentialité native et sécurité graduée | Validé |
| **D7** | Option C — Paramètres hiérarchisés et résilience supervisée | Validé |

Toutes les décisions ci-dessus sont validées. Aucun arbitrage fonctionnel D1–D7 ne reste en attente.

---

## 3. D1 — Architecture locale structurée, versionnée et résiliente

### 3.1. Principe

OSIA suit une approche **local-first** : l'utilisateur conserve ses investigations et ses paramètres sur l'hôte Linux choisi (poste ou serveur), sans compte cloud OSIA ni service cloud obligatoires. PostgreSQL et le stockage de preuves sont gérés par le backend. Le mode serveur impose une authentification (T5.7). Les recherches OSINT et les modèles IA distants peuvent néanmoins nécessiter une connexion réseau : **local-first ne signifie pas fonctionnement intégralement hors ligne**.

### 3.2. Exigences validées

1. **Persistance locale** des investigations entre sessions de navigateur, sans obligation d'export manuel après chaque usage.
2. **Séparation logique** des catégories suivantes : configuration ; investigations et branches ; entités et relations ; sources et pièces conservées ; synthèses et conclusions ; annotations, validations et autres décisions humaines ; historiques techniques et d'investigation.
3. **Enregistrement progressif** de l'avancement, avec conservation du dernier état cohérent lorsque l'application ou l'investigation est interrompue.
4. **Écritures cohérentes** évitant, autant que possible, des relations orphelines ou des états partiellement enregistrés ; détection et signalement des écritures incomplètes.
5. **Versionnement des schémas** et mécanismes de migration contrôlés pour les évolutions futures.
6. **Détection des erreurs** de stockage, de quota, de compatibilité et de migration ; pas de réinitialisation destructive silencieuse.
7. **Pas de transmission distante des données locales** en dehors de ce qui est nécessaire et autorisé pour les fonctions utilisées, avec information adaptée de l'utilisateur.
8. Conservation de la **provenance** des informations et de l'historique des décisions selon les engagements des lots précédents.

### 3.3. Décisions techniques applicables

T2 retient PostgreSQL pour l'état structuré et un stockage de fichiers dédié pour les preuves, avec déduplication SHA-256. T3 impose un moteur Python indépendant des interfaces. Les hypothèses initiales de persistance métier dans `IndexedDB` sont remplacées ; une éventuelle préférence d'affichage côté navigateur n'a pas autorité sur les données ou les budgets.

La persistance sur l'hôte ne remplace pas une sauvegarde cohérente indépendante. Les emplacements, permissions et mécanismes de sauvegarde suivent T2.

---

## 4. D2 — Configuration multi-fournisseurs IA avec orchestration supervisée

### 4.1. Principe

OSIA peut utiliser plusieurs fournisseurs IA et plusieurs modèles, cloud ou locaux lorsqu'ils sont compatibles, sans imposer un prestataire unique. Une configuration initiale avec Mistral est possible, mais ne doit pas conditionner l'architecture.

### 4.2. Configuration des fournisseurs et modèles

- Ajouter, modifier, activer, désactiver et tester un fournisseur.
- Renseigner les informations nécessaires à sa connexion : point d'accès API, modèles disponibles, identifiants ou clé selon le fournisseur.
- Définir un fournisseur et un modèle principaux, ainsi que des alternatives **explicitement autorisées**.
- Affecter des modèles aux rôles utiles : sélection de sources, extraction, analyse, rapprochement/vérification, synthèse, etc.
- Autoriser une orchestration supervisée des modèles selon la tâche, les capacités, la disponibilité, les préférences et les coûts.
- Permettre, si souhaité, de faire fonctionner l'ensemble des tâches avec un modèle unique.

### 4.3. Secrets et identifiants

- **Aucune persistance durable des clés API par défaut** : conservation temporaire en mémoire selon la session autorisée ; la durée de cette session et son articulation avec le service serveur seront spécifiées, sans persistance implicite.
- Conservation persistante **facultative** dans un stockage local chiffré, déverrouillé par phrase secrète.
- Clés masquées dans l'interface et exclues des journaux, diagnostics et exports, y compris des archives `.osia` et des exports de configuration.
- Vérification de connexion sur action explicite, avec erreurs utiles mais sans divulgation de secrets.
- Les informations d'identification d'un fournisseur ne doivent pas être envoyées à un autre fournisseur sans nécessité technique explicitée et autorisée.

### 4.4. Orchestration et garde-fous

- Toute sélection ou bascule entre modèles reste soumise aux autorisations et aux plafonds du **gestionnaire de budgets indépendant** défini en lot B.
- Un repli automatique n'est permis **que** vers une alternative préalablement autorisée, et ne peut pas contourner un budget ou une restriction.
- Un changement de modèle ne justifie pas un appel payant supplémentaire en dehors de l'enveloppe autorisée.
- Toute tentative de connexion susceptible d'engendrer un coût doit respecter les règles de contrôle des opérations payantes, y compris les tests de connexion si le fournisseur les facture.

### 4.5. Limites techniques explicites

Le backend OSIA constitue désormais le composant obligatoire de traitement : les appels modèles passent par le courtier centralisé et les connecteurs par les politiques du moteur (T3, T8.1). Le frontend ne lance pas directement ces appels. Aucun backend cloud OSIA n'est imposé ; le moteur est installé sur le poste ou le serveur choisi.

---

## 5. D3 — Profils de recherche avec limites ajustables

### 5.1. Principe

OSIA propose des **profils de recherche préconfigurés et personnalisables** plutôt que des modes de fonctionnement rigides. Chaque lancement d'investigation permet d'appliquer un profil puis de modifier les limites autorisées.

### 5.2. Profils initiaux proposés

| Profil | Plage de profondeur indicative | Usage indicatif |
|---|---:|---|
| Rapide | 1–2 rebonds | Vérification ciblée |
| Standard | 3–5 rebonds | Recoupement et exploration courante |
| Approfondie | 6–10 rebonds | Investigation relationnelle étendue |

Ces plages constituent des **propositions de préréglages**, pas des contraintes empêchant la personnalisation. Les exemples de montants financiers ou de nombres d'opérations utilisés lors du cadrage sont illustratifs et ne constituent **ni des tarifs, ni des plafonds validés**.

### 5.3. Paramètres ajustables

- Profondeur maximale de **1 à 10 rebonds relationnels** pour l'investigation ou la branche concernée.
- Budget financier maximal pour les opérations payantes.
- Réglages personnalisables du nombre d'opérations, de sources explorées et de branches actives. Les champs de surcharge peuvent être facultatifs, mais les garde-fous effectifs de volume, concurrence et branches restent obligatoires selon A.9/T4.8.
- Durée maximale facultative.
- Fournisseurs IA, modèles et familles de sources autorisés.
- Profils personnalisés, enregistrables et réutilisables.

### 5.4. Hiérarchie des budgets et autorisations

Les limites s'appliquent aux niveaux : **global → investigation → branche → opération**.

- Une limite inférieure ne peut jamais lever un plafond de niveau supérieur.
- Le gestionnaire indépendant vérifie les permissions, **réserve** les enveloppes nécessaires avant les appels payants et suit les dépenses estimées, réservées et constatées lorsque disponibles.
- Les appels parallèles, les nouvelles branches, les nouvelles tentatives et les bascules de modèle sont inclus dans ces contrôles.
- Afficher clairement les enveloppes disponibles, engagées et consommées, ainsi que les avertissements à l'approche d'un plafond.
- Si une limite est atteinte : arrêter les opérations concernées et préserver les résultats acquis.
- Une prolongation ou une augmentation de budget exige une **validation explicite** ; jamais de dépassement tacite.
- Lorsque l'objectif est atteint avant la profondeur maximale : arrêt de l'investigation et **proposition** de pistes supplémentaires, sans lancement ni consommation non autorisés (lot A).

---

## 6. D4 — Conservation différenciée, cache intelligent et nettoyage supervisé

### 6.1. Distinction fondamentale

Deux classes de données ont des règles de cycle de vie distinctes.

**A. Dossier d'investigation (données de référence)**

Comprend notamment : investigations, branches, entités, liens, états du graphe, sources et éléments de preuve conservés, références et provenance, conclusions, contradictions, annotations et décisions humaines, historique et contexte de production.

- **Pas d'expiration ni de suppression automatique par défaut.**
- Conservation jusqu'à action explicite de suppression, sous réserve des obligations légales applicables.
- Les états « actif », « terminé » et « archivé » organisent l'affichage ; **archiver n'est pas supprimer**.
- Les données ayant contribué à une conclusion ou à une décision demeurent traçables tant que l'investigation correspondante est conservée.

**B. Cache technique (données temporaires)**

Comprend notamment : résultats de requêtes transitoires, réponses API réutilisables non promues en éléments de preuve, données intermédiaires de traitements et caches d'accès aux sources.

- Durées de validité **configurables** selon la nature des informations.
- Expiration et purge, y compris automatique, possibles **uniquement** si les données ne sont pas nécessaires à la traçabilité des investigations conservées.
- Possibilité de protéger certains éléments de la purge et de prévisualiser les gains d'espace d'un nettoyage manuel.

### 6.2. Réutilisation et déduplication

- Réutilisation locale des résultats entre branches et entre investigations lorsque leur contexte, leur provenance, leur fraîcheur et les droits d'utilisation le permettent.
- Déduplication raisonnée des contenus sans suppression des références distinctes à leurs origines et dates d'obtention.
- Affichage de la date de collecte, de la dernière actualisation et d'une indication de fraîcheur/obsolescence.
- Une donnée ancienne peut être réutilisée avec son contexte ou signalée comme à actualiser ; elle ne doit **pas** être présentée comme nécessairement actuelle.

### 6.3. Actualisation et historique

- L'utilisateur peut demander une actualisation ; les suggestions d'actualisation n'autorisent pas à elles seules des coûts supplémentaires.
- Lorsqu'une donnée a servi d'élément de preuve, son actualisation ne doit pas en effacer silencieusement la version historique.
- Les nouvelles informations peuvent déclencher la **réévaluation locale des conclusions dépendantes**, avec respect des autorisations si une nouvelle opération externe est nécessaire.
- Toute recherche ou tout appel IA payant suit B6/D3, même lorsqu'il vise seulement à rafraîchir un résultat.

### 6.4. Droits des sources

Le maintien de la provenance n'impose pas une copie intégrale de chaque page web. Les contenus capturés ou intégrés aux archives doivent respecter les conditions d'utilisation et les règles applicables ; à défaut, conserver les références, métadonnées et extraits utilisables dans les limites permises.

### 6.5. Règle intangible

> **L'expiration du cache ne peut jamais provoquer la disparition d'une information nécessaire à l'étayage d'une conclusion ou à la traçabilité d'une décision humaine tant que l'investigation correspondante est conservée.**

---

## 7. D5 — Archives portables, export HTML autonome et restauration supervisée

### 7.1. Deux formats aux usages distincts

**A. Archive OSIA `.osia` — portabilité et restauration de dossiers**

- Format d'archive **documenté, versionné et ouvert dans sa spécification**.
- Export d'une investigation et de toutes ses branches/dépendances nécessaires ; d'une sélection d'investigations ; ou export logique complet des données persistantes exportables et paramètres non sensibles. Cet export ne remplace pas la sauvegarde technique de l'installation (T7.9).
- Préservation de la structure nécessaire à la reprise : identifiants, relations, métadonnées, dates, graphes, références/captures de sources lorsque exportables, conclusions, décisions humaines et historique.
- Manifeste de version, inventaire du contenu et contrôles d'intégrité.
- Orientation retenue en T7.1 : conteneur ZIP64, données JSON/JSONL et documents originaux. Le schéma, les règles d'interopérabilité et les enveloppes de chiffrement restent à spécifier ; le format est ouvert et documenté.
- L'archive peut être **chiffrée facultativement** par une phrase secrète.
- **Exclusion systématique des clés API, jetons et autres secrets** de la sauvegarde exportée.

**B. Page HTML autonome `.html` — restitution et partage**

- Export **inspiré du fonctionnement de Scoreboard**, sous la forme privilégiée d'un **fichier HTML unique** autonome, consultable localement dans un navigateur et hors connexion.
- Restitution **interactive, en lecture seule** : graphe zoomable et navigable, arbre d'investigation et branches, détails des entités et relations, synthèses et conclusions, niveaux d'étayage/confiance selon le lot C, contradictions, sources, recherche et filtres pertinents.
- Les ressources nécessaires à la consultation sont intégrées localement autant que les contraintes de taille et de compatibilité le permettent ; si des pièces volumineuses imposent des fichiers associés, l'utilisateur est averti et choisit le mode d'export adapté.
- **Aucun appel IA, aucune synchronisation ni requête réseau automatique** lors de l'ouverture du rapport autonome. Les liens externes éventuels ne sont ouverts que par une action volontaire de consultation.
- Ce format est une **photographie consultable** de l'investigation au moment de l'export, et **n'est pas** le format de restauration/modification du dossier.
- Options d'inclusion, exclusion et **suppression effective du fichier généré** des données confidentielles : coordonnées personnelles, notes privées, identifiants, pièces ou autres catégories selon les données présentes. Une information exclue ne doit pas être simplement cachée visuellement dans le HTML.
- Neutralisation des contenus non fiables issus des sources (notamment pour éviter l'exécution de scripts injectés) ; pas de chargement automatique de scripts tiers.
- Un HTML non chiffré doit être clairement présenté comme **lisible par toute personne possédant le fichier**.

**C. Export combiné**

Une commande **« Exporter les deux »** permet de produire, en une opération utilisateur, l'archive `.osia` destinée à la reprise et le rapport `.html` destiné à la consultation.

### 7.2. Import et restauration

- Validation du type de fichier, de la version, de la structure et de l'intégrité avant importation.
- **Prévisualisation** des données et de leur portée avant toute modification locale.
- Détection des doublons, des collisions d'identifiants, des versions et des conflits.
- Modes distincts : **ajouter**, **fusionner de façon supervisée** ou **restaurer complètement** lorsque l'opération est compatible.
- La fusion ne doit jamais écraser silencieusement les éléments existants ou l'historique de validation ; les conflits sont explicités et soumis à résolution.
- Une restauration complète susceptible de remplacer les données existantes demande confirmation et doit proposer, lorsque possible, une sauvegarde préalable de l'état courant.
- Migration d'archive ancienne seulement si un chemin sûr et compatible existe. En cas d'incertitude, refuser l'import destructif plutôt que tenter une conversion hasardeuse.
- L'import/restauration n'enclenche **aucune reprise de recherche ni opération IA payante automatique**.
- Une archive restaurée doit restituer les informations et états enregistrés **sans exiger de nouvelles requêtes IA**.

### 7.3. Sauvegarde automatique versus sauvegarde externe

- **Enregistrement automatique local** des travaux : prévu par D1.
- **Sauvegarde externe portable** : disponible manuellement dès le périmètre initial.
- Sauvegarde technique manuelle et programmation facultative : capacité validée en T2.5, destination et rétention configurables. La [V1](../PERIMETRE-V1.md) livre la sauvegarde manuelle. La programmation facultative est reportée.
- Ne pas présenter l'enregistrement dans PostgreSQL et le répertoire de preuves comme une sauvegarde indépendante.

### 7.4. Intégrité ≠ authenticité

Les sommes de contrôle détectent des corruptions ou altérations mais ne prouvent pas, à elles seules, l'identité de l'auteur ni l'absence de falsification. Une signature cryptographique d'auteur constitue une fonction distincte, **non validée ici comme exigence de D5**.

### 7.5. Règles intangibles

> **Une investigation sauvegardée est restaurable avec ses branches, graphe, sources, conclusions et historique de décisions, sans nouveaux appels IA.**

> **Aucun import ni restauration ne peut effacer ou remplacer silencieusement les données existantes.**

---

## 8. D6 — Confidentialité native et sécurité graduée

### 8.1. Protection par défaut

- Données conservées **sur l'hôte choisi par défaut**, sans compte cloud OSIA ni synchronisation distante obligatoire. Les accès serveur restent authentifiés selon T5.7.
- Absence de télémétrie imposée.
- Transmissions externes restreintes aux usages et fournisseurs/connecteurs **autorisés**, avec lisibilité des services destinataires et des catégories de données communiquées.
- Possibilité de désactiver des fournisseurs, connecteurs et catégories de transmission.
- Application des protections des clés API de D2 ; aucun secret en clair dans les journaux, diagnostics ou exports.

### 8.2. Sécurité renforcée facultative

- **Coffre-fort local chiffré** activable par l'utilisateur, avec phrase secrète et opérations de chiffrement/déchiffrement locales.
- Verrouillage manuel et après inactivité configurable.
- Le chiffrement est une protection des données **au repos**, non une garantie contre toutes les attaques lors d'une session déverrouillée.
- Préciser les conséquences de la perte de phrase secrète et les possibilités réelles de récupération, sans promettre de récupération impossible.

### 8.3. Protection des exports

- Archives `.osia` chiffrables sur choix utilisateur.
- Rapports HTML : **sélection et minimisation** des informations intégrées ; possibilité d'exclure effectivement coordonnées, notes privées et autres données sensibles.
- Le HTML autonome en clair reste lisible par ses détenteurs. L'application doit avertir l'utilisateur avant un export susceptible de contenir des données sensibles.
- Les ressources internes du rapport ne doivent pas charger de scripts distants. Les contenus non fiables sont traités comme des **données**, pas comme du code exécutable.

### 8.4. Cycle d'effacement

Actions distinctes :

1. **Archiver :** retirer des vues courantes sans suppression, opération réversible.
2. **Supprimer une investigation :** confirmation explicite ; analyse des dépendances et des éléments partagés pour éviter d'affecter les autres investigations conservées.
3. **Effacer toutes les données locales OSIA :** confirmation renforcée ; vise investigations, cache, paramètres et éventuels secrets conservés.

Les journaux techniques peuvent être purgés séparément ; la purge ne doit pas rendre incohérents les historiques d'investigation encore conservés.

**Limite :** OSIA ne peut garantir l'effacement physique des blocs d'un SSD, d'anciennes sauvegardes, de copies déjà exportées ni des données conservées indépendamment par des tiers. Cette limite doit être expliquée clairement.

### 8.5. Données OSINT et obligations applicables

Le caractère public d'une source ne dispense pas automatiquement de respecter les obligations relatives aux données personnelles (notamment le RGPD lorsque applicable). Les choix d'implémentation doivent prendre en compte minimisation, finalité, durées adaptées, sécurité et conditions d'utilisation des sources, en fonction du contexte d'usage. Le présent cadrage n'affirme pas que tous les traitements OSINT sont légalement autorisés dans toutes les situations.

### 8.6. Règle intangible

> **L'utilisateur garde le contrôle des données locales, des informations transmises aux services externes et du contenu réellement inclus dans les exports.**

---

## 9. D7 — Paramètres hiérarchisés et résilience supervisée

### 9.1. Organisation des paramètres

Une interface centrale regroupe a minima :

- **Général :** langue, affichage, comportement et préférences.
- **Intelligence artificielle :** fournisseurs, modèles, clés API, affectation de rôles, alternatives.
- **Sources et connecteurs :** catalogue, accès, autorisations et restrictions.
- **Investigations et budgets :** profils, profondeur, plafonds et limites.
- **Données et stockage :** cache, conservation, exports, sauvegardes et restauration.
- **Confidentialité et sécurité :** coffre-fort, verrouillage, permissions, effacement.
- **Diagnostics :** état des services, erreurs, compatibilité et journaux.

Cette organisation est **fonctionnelle** : sa réalisation visuelle détaillée appartient à l'étape de conception.

### 9.2. Hiérarchie de configuration

**Valeurs appliquées :** paramètres globaux → profil choisi → paramètres explicitement validés de l'investigation → ajustements validés de la branche.

**Restrictions :** chaque niveau inférieur doit respecter les plafonds et interdictions des niveaux supérieurs. Les restrictions globales de sécurité nouvellement appliquées valent pour les **futures opérations** concernées, sans effacer l'historique de ce qui a été fait.

- Conserver la **configuration effective** (instantané/version) ayant régi l'investigation ou une branche pour comprendre et reproduire le contexte de production des résultats.
- Les modifications ultérieures des valeurs globales ou d'un profil ne modifient **pas rétroactivement** le budget ni les règles déjà accordées à une investigation.
- Les nouveaux paramètres demandés pour une prolongation ou une branche requièrent validation explicite avant lancement.
- Un nouveau plafond global restrictif peut **bloquer de futures opérations**, même si une investigation utilisait auparavant une configuration plus permissive.

### 9.3. Gestion des modifications de paramètres

- Vérification de validité des valeurs avant enregistrement.
- Historique des modifications importantes, notamment celles qui affectent permissions, budgets et confidentialité.
- Retour aux valeurs par défaut possible, sans destruction silencieuse des travaux.
- Import/export de configuration **versionnée et sans secrets**.
- Messages expliquant quels paramètres sont hérités, surchargés ou bloqués par un plafond supérieur.

### 9.4. Gestion des erreurs et récupération

| Incident | Comportement attendu |
|---|---|
| Fournisseur/API indisponible | Mise en attente et/ou tentative contrôlée si déjà autorisée ; alternative uniquement autorisée |
| Clé expirée/refusée | Arrêt des opérations concernées ; invitation à corriger la configuration |
| Quota ou budget atteint | Arrêt des appels payants concernés ; conservation des résultats partiels |
| Source indisponible | Signalement ; proposition d'alternatives autorisées, sans dépense imprévue |
| Perte du réseau | Conservation locale de l'état ; reprise possible lorsque les conditions sont réunies |
| Stockage saturé | Alerte, préservation des données cohérentes, nettoyage ciblé proposé |
| Données incohérentes / migration incompatible | Diagnostic et isolation lorsque possible ; aucune purge ou réinitialisation destructive automatique |
| Investigation interrompue | Reprise depuis le dernier état cohérent, avec vérification des droits, paramètres et budgets |
| État/facturation d'un appel incertains | **Ne pas réessayer aveuglément** ; vérifier l'état et les risques de double traitement/coût |

- Les tentatives automatiques ne sont possibles que si l'opération est sûre, compatible avec les autorisations et dans les limites prévues.
- Les mécanismes de reprise ne doivent pas générer de doubles dépenses ni réexécuter des opérations à effet externe lorsque leur résultat est incertain sans vérification adaptée.
- Présenter les erreurs dans un langage compréhensible, accompagnées d'actions concrètes.
- Les diagnostics et journaux restent locaux par défaut et sont **expurgés de secrets** ; un export de diagnostic expurgé peut être proposé.
- Quand c'est possible, proposer un export de secours des données cohérentes avant une réparation à risque.

### 9.5. Trois propriétés obligatoires

1. **Reproductibilité du contexte :** conserver les paramètres réellement utilisés pour produire les résultats (sans promettre une reproduction identique de contenus web ou de modèles externes qui évoluent).
2. **Résilience :** une erreur ne doit pas entraîner la perte des résultats déjà enregistrés de façon cohérente.
3. **Supervision :** aucun mécanisme de correction/reprise ne contourne les autorisations, dépenses maximales ou validations humaines.

---

## 10. Exigences transversales non négociables

Les règles suivantes s'appliquent à l'ensemble du lot D :

| ID | Règle |
|---|---|
| **D-INV-01** | Aucune dépense payante hors permission et enveloppe accordées ; budget contrôlé par une couche indépendante de l'IA. |
| **D-INV-02** | Aucune investigation, branche ou prolongation lancée implicitement par une modification de configuration, un import ou un rapport HTML. |
| **D-INV-03** | Conservation des sources/provenances et décisions nécessaires à la traçabilité, en cohérence avec les lots A–C. |
| **D-INV-04** | Aucune suppression, fusion ou restauration destructive sans confirmation et traitement des dépendances. |
| **D-INV-05** | Aucun secret API dans les rapports, archives, exports de paramètres, journaux ou diagnostics. |
| **D-INV-06** | L'export HTML est autonome, consultable hors ligne, en lecture seule et sans accès réseau automatique. |
| **D-INV-07** | Une archive `.osia` vise la restauration fidèle de l'investigation ; un HTML vise sa consultation, pas sa reprise. |
| **D-INV-08** | Pas de backend distant, compte OSIA ou synchronisation obligatoire pour conserver et consulter localement les investigations. |
| **D-INV-09** | Tout changement global préserve l'historique de configuration et ne change pas silencieusement les règles des investigations existantes. |
| **D-INV-10** | Les mécanismes d'erreur, reprise, purge et migration privilégient la conservation du dernier état cohérent. |

## 11. Parcours fonctionnels de référence

### 11.1. Démarrer une investigation

1. Choisir un profil ou une configuration personnalisée.
2. Voir profondeur, sources, modèles et budgets autorisés.
3. Valider explicitement les paramètres d'exécution et l'enveloppe applicable.
4. Enregistrer un instantané des paramètres effectifs.
5. Démarrer l'investigation sous supervision du gestionnaire indépendant des autorisations et coûts.
6. Enregistrer progressivement les sources, graphes, résultats et décisions.

### 11.2. Reprendre après interruption

1. Détecter l'état interrompu et le dernier point cohérent.
2. Présenter l'état des opérations terminées, en cours ou incertaines.
3. Vérifier la compatibilité des paramètres, autorisations et budgets encore valables.
4. Reprendre seulement les opérations sûres et autorisées, sans double exécution aveugle.
5. Conserver l'historique de l'interruption et des actions de récupération.

### 11.3. Exporter et partager

1. Choisir « archive `.osia` », « HTML autonome » ou « les deux ».
2. Vérifier la sélection des investigations/branches et les données incluses.
3. En cas de HTML, choisir quelles données privées/sensibles retirer **réellement** du document.
4. En cas d'archive, choisir éventuellement un chiffrement avec phrase secrète.
5. Générer les fichiers sans secrets API ni appel IA nécessaire.
6. Permettre la consultation HTML hors ligne ou l'import `.osia` dans OSIA.

### 11.4. Importer une archive

1. Lire et valider manifeste, version, intégrité et structure.
2. Prévisualiser investigations, documents, branches, historique et conflits.
3. Choisir ajout, fusion supervisée ou restauration intégrale.
4. Confirmer les changements ; proposer une sauvegarde préalable si risque d'écrasement.
5. Effectuer l'import de façon cohérente, sans lancer de recherche ni d'appel payant.
6. Signaler clairement les éléments importés, ignorés, migrés ou en conflit.

## 12. Critères de recette fonctionnelle

Les tests ci-dessous servent à vérifier que l'implémentation respecte les décisions validées ; ils ne figent pas la technologie employée.

- [ ] **REC-D1-01** : fermer et rouvrir OSIA retrouve une investigation, ses branches, ses sources et ses décisions enregistrées.
- [ ] **REC-D1-02** : une interruption durant l'écriture ne produit pas de restauration silencieusement incohérente.
- [ ] **REC-D2-01** : configurer deux fournisseurs et affecter des modèles à des tâches distinctes.
- [ ] **REC-D2-02** : une clé API absente de la mémoire persistante par défaut ne figure ni dans les exports ni dans les journaux.
- [ ] **REC-D2-03** : une alternative de modèle non autorisée ne peut être utilisée automatiquement.
- [ ] **REC-D3-01** : un profil personnalisé et des limites d'investigation sont enregistrés et appliqués.
- [ ] **REC-D3-02** : aucune nouvelle dépense OSIA ne peut être engagée au-delà de l'autorisation même lors d'appels parallèles ou de relances ; les écarts de facture fournisseur restent distingués et visibles (T8.4).
- [ ] **REC-D4-01** : purger le cache temporaire ne détruit pas une preuve nécessaire à une conclusion conservée.
- [ ] **REC-D4-02** : une actualisation préserve la provenance et l'ancienne version probante.
- [ ] **REC-D5-01** : exporter puis réimporter un `.osia` restitue branches, graphe, sources et historique sans nouveaux appels IA.
- [ ] **REC-D5-02** : un conflit d'import est détecté et ne provoque aucun écrasement silencieux.
- [ ] **REC-D5-03** : un `.html` exporté s'ouvre hors ligne, permet la navigation interactive et ne déclenche aucun appel externe automatique.
- [ ] **REC-D5-04** : les données désélectionnées d'un HTML sont réellement absentes du fichier produit.
- [ ] **REC-D5-05** : une archive chiffrée requiert le déverrouillage ; une archive corrompue est refusée avec diagnostic.
- [ ] **REC-D6-01** : les transmissions externes respectent les connecteurs/fournisseurs autorisés.
- [ ] **REC-D6-02** : les modes archive, suppression et effacement global ont des portées distinctes, explicites et confirmées.
- [ ] **REC-D7-01** : modifier un profil global n'augmente pas le budget d'une investigation déjà lancée.
- [ ] **REC-D7-02** : une nouvelle restriction globale empêche les opérations futures incompatibles sans réécrire l'historique.
- [ ] **REC-D7-03** : une erreur réseau, API ou stockage conserve les résultats déjà enregistrés et offre une résolution supervisée.

## 13. Questions laissées à la conception technique

Ces sujets sont **volontairement ouverts** ; ils ne constituent pas des arbitrages fonctionnels supplémentaires :

- Schémas, index, transactions et migrations PostgreSQL ; le choix de la base est clos (T2.1).
- Schéma exact des archives ZIP64/JSON/JSONL, profil de chiffrement authentifié et sérialisation dans le respect de T7.3 (AES-256-GCM cité comme exemple, Argon2id retenu pour la dérivation depuis une phrase secrète), métadonnées et gros documents.
- Contrats des adaptateurs et de l'API du moteur obligatoire ; aucun appel modèle direct du frontend.
- Liste concrète des fournisseurs, modèles, connecteurs et capacités supportés à la première version.
- Valeurs par défaut des budgets, seuils d'alerte et TTL des caches ; les valeurs présentées pendant le cadrage n'étaient que des exemples.
- Formats complémentaires de restitution éventuellement proposés en plus du HTML et des archives, sous réserve du lot C.
- Mécanismes exacts de détection de duplicats, de gestion des conflits, de vérification d'idempotence et de reprise d'opérations incertaines.
- Paramètres et mécanisme de sauvegarde technique cohérente à chaud, avec programmation facultative selon T2.5–T2.6.
- Revue juridique adaptée aux types de données effectivement collectées, aux sources utilisées et aux usages visés.

## 14. Périmètre non imposé par ce lot

Les décisions D1–D7 **n'imposent pas** :

- une infrastructure cloud OSIA, un serveur central ou la création d'un compte ;
- une synchronisation automatique entre appareils ;
- un chiffrement obligatoire de toutes les données locales ;
- la signature électronique des archives et rapports ;
- l'utilisation simultanée de plusieurs modèles pour chaque tâche ;
- une sauvegarde périodique externe dès la version initiale ;
- une conservation illimitée de tout cache technique ;
- une garantie d'effacement physique des supports et sauvegardes externes ;
- la garantie de reproductibilité identique des réponses de services externes dans le temps.

---

## 15. Clôture et suite du projet

Le **lot D « Paramètres et données locales » est clôturé** le **5 novembre 2026**, avec **sept arbitrages validés**, tous en option C, dont **D5 en option C enrichie** (archive restaurable `.osia` + export HTML autonome interactif à la manière de Scoreboard).

Les lots de cadrage fonctionnel **A, B, C et D** constituent désormais le socle de référence pour préparer une **conception technique transversale**, puis le développement. Toute divergence future avec une décision validée doit être rendue explicite et faire l'objet d'un nouvel arbitrage, plutôt que d'être introduite implicitement dans l'implémentation.

**Fin du lot D — édition consolidée 1.1.**
