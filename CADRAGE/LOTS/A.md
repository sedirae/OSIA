# OSIA — Cadrage fonctionnel

> **Édition consolidée : 1.1 — 06/11/2026.** Les arbitrages conservent leur validation initiale. Cette édition harmonise les formulations avec les lots ultérieurs ; elle ne vaut pas attestation de développement. Références : [index](../README.md), [résolutions de cohérence](../AUDIT-COHERENCE.md), [registre des décisions](../../COWORKAI/DECISIONS.md).

## Lot A — Moteur d'investigation

**Édition 1.1 — 6 novembre 2026 ; décisions validées le 5 novembre 2026**  
**Statut : référence fonctionnelle consolidée et validée sur ses principes**  
**Nature :** cahier des charges fonctionnel, destiné à la lecture humaine et à l'utilisation par des agents IA. **Ce document n'est pas une spécification d'architecture ni une consigne de développement.**

---

## 0. Objet du document

Ce document rassemble les décisions prises lors de l'étude de faisabilité et des échanges de cadrage fonctionnel du **lot A**. Il décrit ce qu'OSIA doit accomplir, les règles de comportement du moteur, les interactions avec l'utilisateur et les résultats attendus.

Il distingue :

- **[VALIDÉ]** : principe ou arbitrage accepté ;
- **[À PRÉCISER]** : détail restant à déterminer lors des lots suivants ou du cadrage technique ;
- **[HORS LOT A]** : sujet mentionné pour assurer la cohérence générale mais à détailler ailleurs.

Ce lot fixe les comportements. Les choix techniques désormais applicables sont définis dans les lots T1 à T8, notamment Python, PostgreSQL et REST/SSE. Les frameworks et algorithmes non arbitrés relèvent de la conception détaillée.

### 0.1. Finalité d'OSIA — [VALIDÉ]

> **OSIA est un moteur d'investigation OSINT intelligent dont la finalité est de répondre à une question ou de rechercher une information à partir d'indices initiaux, en collectant, croisant et mettant en relation des données issues de sources publiques.**
>
> Le moteur explore automatiquement les pistes pertinentes par rebonds successifs, conserve les découvertes secondaires et permet à l'utilisateur d'affiner l'investigation par validation, rejet ou approfondissement de correspondances.
>
> Les conclusions sont étayées par des sources vérifiables et distinguent les faits établis, les hypothèses et les incertitudes.

**Conséquence essentielle :** OSIA ne cherche pas à accumuler le maximum de données ; elle cherche à **produire une réponse utile et justifiée à un objectif de recherche**. Une investigation peut également être exploratoire lorsqu'aucun objectif n'est formulé.

### 0.2. Philosophie d'usage — [VALIDÉ]

- OSIA accélère le travail d'investigation réalisé sur des sources publiques ; elle ne sert pas à accéder à des comptes, espaces ou données privés.
- L'IA conduit l'exploration et propose des interprétations ; elle ne transforme pas une hypothèse en fait simplement parce qu'elle la juge plausible.
- L'utilisateur reste maître des corrections, prolongations et dépenses dépassant les limites initiales.
- Les données collectées, leurs sources, les hypothèses et les conclusions doivent rester distinguables.
- La conception privilégie un produit léger, sans compte cloud OSIA imposé ni gestion collaborative multi-utilisateur requise en V1. Le mode serveur impose cependant une authentification et des autorisations selon T5.7.

---

## 1. Glossaire fonctionnel

| Terme | Définition retenue |
|---|---|
| **Indice initial** | Information fournie par l'utilisateur pour amorcer une investigation : nom, adresse, entreprise, identifiant, URL, etc. |
| **Objectif** | Question ou information que l'utilisateur cherche à obtenir. Il oriente l'investigation sans constituer une preuve. |
| **Sous-objectif** | Question dérivée de l'objectif principal, nécessaire ou utile pour y répondre. |
| **Entité** | Personne, entreprise, organisation, lieu, domaine, profil ou autre objet individualisé dans les résultats. |
| **Identité / résolution d'entité** | Détermination du fait que deux références désignent ou non une même entité. |
| **Relation** | Lien d'une nature déterminée entre deux ou plusieurs entités : juridique, professionnelle, géographique, historique, etc. |
| **Correspondance** | Association proposée entre références ou entités, éventuellement incertaine et soumise à validation/rejet. |
| **Piste** | Hypothèse ou nouvel indice susceptible de justifier une recherche complémentaire. |
| **Recherche initiale (niveau 0)** | Collecte et première analyse réalisées à partir des indices fournis, avant tout rebond. |
| **Rebond** | Nouvelle génération d'exploration déclenchée par une découverte de la génération précédente ; ce n'est pas un appel API individuel. |
| **Branche** | Approfondissement dérivé d'une investigation, avec son objectif et ses limites propres, mais exploitant les connaissances déjà obtenues. |
| **Connaissances communes** | Informations collectées et sourcées, réutilisables entre les branches d'une même investigation. |
| **Conclusion** | Réponse argumentée à l'objectif d'une branche, distincte des données brutes et des hypothèses. |
| **Investigation incomplète** | Recherche arrêtée sans avoir nécessairement épuisé les sources ou atteint tous ses sous-objectifs. |

---

## 2. Parcours fonctionnel de référence

**[VALIDÉ]** Parcours général :

1. L'utilisateur renseigne un ou plusieurs **indices de départ** et, s'il le souhaite, un **objectif** rédigé en une courte phrase.
2. OSIA interprète les indices et l'objectif, détecte les ambiguïtés et décompose l'objectif en sous-questions pertinentes.
3. OSIA sélectionne, parmi les sources activées et disponibles, celles qui semblent utiles, puis lance la **recherche initiale (niveau 0)**.
4. OSIA identifie les entités, rapproche les résultats, documente les relations et distingue preuves, probabilités et pistes à vérifier.
5. Le moteur identifie les informations manquantes, hiérarchise les pistes et lance automatiquement les **rebonds** autorisés.
6. À chaque génération, OSIA réévalue la progression vers l'objectif, les opportunités d'approfondissement et les limites de consommation.
7. OSIA arrête la recherche lorsqu'une réponse suffisamment étayée est obtenue, qu'aucune piste pertinente ne justifie sa poursuite ou qu'une limite/condition d'arrêt intervient.
8. Elle produit une **réponse synthétique**, un **graphe relationnel** et des **fiches de résultats sourcées**.
9. Elle conserve les pistes non explorées et, lorsqu'elles présentent un intérêt, **suggère des approfondissements**.
10. L'utilisateur peut valider ou rejeter des correspondances, corriger des identifications et ouvrir une **nouvelle branche** d'investigation sans repartir de zéro.

Le parcours est automatique jusqu'à l'arrêt ; il ne nécessite pas une validation intermédiaire à chaque rebond.

---

## 3. A.1 — Comprendre les indices et l'objectif

### A.1.1. Saisie — [VALIDÉ]

L'interface de recherche doit proposer :

- **Informations de départ** : saisie libre d'un ou plusieurs indices combinables.
- **Objectif de l'investigation** : courte phrase en langage naturel, **facultative**.

Exemples d'indices : identité, entreprise, adresse postale, courriel, téléphone, pseudonyme, domaine ou URL, identifiant SIREN/SIRET/ORCID, référence documentaire ou autre élément exploitable.

Exemple :

- **Indice** : « 12 rue Exemple, Reims ».
- **Objectif** : « Quels liens existent entre les entreprises domiciliées à cette adresse ? ».

Sans objectif : OSIA conduit une investigation exploratoire à partir des indices. Avec objectif : celui-ci devient le **fil conducteur prioritaire**, sans interdire la découverte de pistes périphériques intéressantes.

### A.1.2. Interprétation — [VALIDÉ]

OSIA doit :

- détecter le type probable des indices ;
- rechercher les ambiguïtés et éviter les identifications prématurées ;
- comprendre le résultat que l'utilisateur souhaite obtenir ;
- interpréter les formulations affirmatives comme des **hypothèses à vérifier**, et non comme des vérités ;
- déterminer les premières familles de sources utiles ;
- construire un plan d'exploration initial qu'elle peut réviser par la suite.

Exemple : « Montrer que A et B appartiennent au même groupe » doit être compris comme « vérifier si A et B appartiennent au même groupe », avec possibilité de ne trouver aucun élément concluant.

### A.1.3. Plusieurs sous-objectifs — [VALIDÉ]

Une seule phrase peut contenir plusieurs questions : « rechercher les liens entre A et B et déterminer s'ils ont déjà partagé des dirigeants ou des locaux ».

OSIA doit pouvoir décomposer cette demande en sous-objectifs et produire ensuite une réponse globale distinguant les réponses à chacun. La complexité de l'investigation reste soumise aux limites de profondeur, de volume et de budget.

### A.1.4. Transparence — [VALIDÉ]

OSIA peut présenter brièvement l'orientation qu'elle a comprise (« recherche des sociétés à cette adresse, de leurs dirigeants et de leurs liens »). Cette information n'est **pas** une étape d'approbation obligatoire avant démarrage.

---

## 4. A.2 — Sélection et interrogation des sources

### A.2.1. Règles de sélection — [VALIDÉ]

- Toutes les **sources configurées et disponibles** sont activées par défaut.
- L'utilisateur peut activer/désactiver individuellement une source.
- Une source **activée** n'est pas forcément **interrogée** : OSIA privilégie celles qui servent l'objectif.
- Une source désactivée ne doit pas être interrogée.
- Une source indisponible, non configurée ou nécessitant une clé absente ne bloque pas l'ensemble de l'investigation.
- OSIA doit, lorsqu'elles existent et sont pertinentes, privilégier les informations provenant de sources officielles et directement vérifiables.
- Les résultats identiques ou équivalents provenant de plusieurs sources doivent être rapprochés, sans faire disparaître leur provenance.

### A.2.2. Familles de sources envisagées — [ORIENTATION VALIDÉE, CATALOGUE À PRÉCISER]

Web public, registres d'entreprises, données institutionnelles françaises et européennes, publications et profils scientifiques, code et profils de développement, pages et profils publiquement accessibles, recherche de pseudonymes et autres répertoires adaptés à l'objectif.

Des services et outils comme OpenAlex, ORCID, GitHub, Sherlock, Hunter, Have I Been Pwned ou Holehe ont été cités **à titre de pistes de faisabilité**, sans décision d'intégration systématique ni garantie de disponibilité. Les contraintes d'accès et les conditions d'utilisation de chaque source doivent être vérifiées lors de son intégration selon B3/B7 et T5.

Une source ou un outil ne doit pas être utilisé pour contourner un accès privé ou réaliser une action incompatible avec le périmètre « sources publiques ».

---

## 5. A.3 — Reconnaissance et résolution des entités

### A.3.1. Identification — [VALIDÉ]

OSIA doit distinguer les entités et leurs attributs : nom, variantes de nom, identifiants connus, coordonnées ou adresses publiques, période de validité et sources justificatives.

Lorsqu'un même objet apparaît sous différentes dénominations, OSIA peut rapprocher les références. Elle ne doit pas fusionner automatiquement des homonymes ou des entreprises partageant une adresse.

### A.3.2. Trois cas — [VALIDÉ]

| Situation | Comportement |
|---|---|
| Identité établie par des éléments suffisants | Regrouper les références dans une même entité, avec preuves conservées |
| Identité vraisemblable, mais non démontrée | Proposer une correspondance qualifiée |
| Identité incertaine ou contradictoire | Garder les entités distinctes et l'incertitude explicite |

**Règle structurante :** « ces deux fiches désignent-elles la même entité ? » et « ces deux entités sont-elles liées ? » sont **deux questions indépendantes**.

---

## 6. A.4 — Relations, preuves et confiance

### A.4.1. Typologie — [VALIDÉ, EXTENSIBLE]

Les relations peuvent notamment être géographiques (même adresse), juridiques ou capitalistiques (participation), organisationnelles (dirigeant commun), professionnelles, scientifiques, numériques ou historiques.

Chaque relation doit disposer d'une **nature explicite** : « partage une adresse » ne doit pas devenir « appartient au même groupe ».

### A.4.2. Qualification — [VALIDÉ]

- **Relation documentée** : un ou plusieurs éléments permettent d'établir la relation précisément décrite.
- **Relation probable** : indices convergents, mais preuve insuffisante pour confirmer.
- **Piste à vérifier** : rapprochement intéressant, encore trop incertain pour conclure.

Ces qualifications s'appliquent à une **proposition de relation précise** et non à toutes les implications qu'on pourrait lui prêter. Exemple : une domiciliation commune peut être documentée, sans établir une relation juridique.

### A.4.3. Indicateur de confiance — [PRINCIPE VALIDÉ, BARÈME À PRÉCISER]

Une **représentation explicable de la confiance**, compatible avec les dimensions de B5/T6.7 et les restrictions de C3-07, peut compléter la qualification en représentant la solidité des éléments disponibles : qualité des sources, concordance, identification des entités, fraîcheur et contradictions.

**Ne pas présenter un score inventé par le modèle comme une probabilité objective.** Les principes de restitution sont fixés par B5, C3 et T6.7 ; règles de calcul, niveaux et visualisation détaillée restent à spécifier.

### A.4.4. Traçabilité — [VALIDÉ]

Toute affirmation importante doit permettre de retrouver :

- la source ou les sources consultées ;
- l'adresse ou la référence du document lorsque disponible ;
- la date de consultation ;
- la date ou période de validité des faits lorsqu'elle peut être établie ;
- la distinction entre information observée, rapprochement et déduction IA.

Une absence de résultat dans les sources interrogées **ne prouve pas** l'inexistence d'une relation.

---

## 7. A.5 — Rebonds et profondeur

### A.5.1. Définition — [VALIDÉ]

- **Niveau 0 :** recherche initiale issue des indices fournis.
- **Rebond 1 :** nouvelles recherches provoquées par les découvertes du niveau 0.
- **Rebond 2 :** nouvelles recherches provoquées par les découvertes du rebond 1.
- Et ainsi de suite, dans la limite choisie.

La profondeur maximale est réglable **de 1 à 10 rebonds**. Elle correspond à un **maximum autorisé**, jamais à un quota devant être intégralement consommé.

Plusieurs recherches et plusieurs appels API peuvent appartenir au même rebond. Le nombre d'appels n'est pas la profondeur.

### A.5.2. Exemple — [ILLUSTRATIF]

- Niveau 0 : trois entreprises A, B et C sont trouvées à l'adresse fournie.
- Rebond 1 : découverte des dirigeants et de l'activité des trois entreprises.
- Rebond 2 : découverte d'une entreprise D dirigée par l'une de ces personnes.
- Rebond 3 : recherche de liens juridiques entre D et les entreprises de départ.

OSIA peut s'arrêter avant le maximum si elle dispose d'une réponse suffisamment étayée ou si les recherches restantes n'ont plus d'intérêt suffisant.

---

## 8. A.6 — Évaluation et priorisation des pistes

### A.6.1. Questions internes — [VALIDÉ]

À chaque cycle, OSIA doit savoir distinguer :

1. les faits déjà établis ;
2. les hypothèses et contradictions ;
3. les informations manquantes pour atteindre l'objectif ;
4. les pistes capables de combler ces manques ;
5. les pistes périphériques intéressantes, mais non prioritaires.

Le plan de recherche est **dynamique** : de nouvelles questions peuvent apparaître à la suite d'une découverte.

### A.6.2. Critères de priorité — [VALIDÉ]

| Critère | Question à se poser |
|---|---|
| Pertinence | La piste contribue-t-elle à l'objectif ou à un sous-objectif ? |
| Fiabilité | Sur quels éléments repose-t-elle ? |
| Nouveauté | Apporte-t-elle autre chose que ce qui est déjà connu ? |
| Potentiel | Est-elle susceptible de combler une lacune ou de révéler une relation importante ? |
| Coût | Son approfondissement est-il raisonnable au regard des limites et de son intérêt ? |

La pertinence **n'est pas** la confiance : une piste peut être fiable mais hors sujet, ou pertinente mais incertaine.

### A.6.3. Deux destinées pour une piste — [VALIDÉ]

- **Exploration prioritaire :** OSIA approfondit la piste automatiquement lorsqu'elle présente un intérêt suffisant et que les limites l'autorisent.
- **Piste secondaire :** OSIA la conserve, la qualifie et peut la suggérer ultérieurement, mais ne la poursuit pas automatiquement.

Une piste peut être écartée de l'exploration automatique si elle est trop éloignée de l'objectif, redondante, peu probante, non productive ou disproportionnée en coût. **Conserver** une piste secondaire ne signifie pas qu'elle constitue un fait établi.

### A.6.4. Rendement de recherche — [VALIDÉ]

Le moteur doit observer si les nouvelles générations apportent réellement des éléments utiles. Une branche durablement infructueuse peut être arrêtée ; cela ne condamne pas les autres branches.

Aucun seuil fixe de type « X % de résultats utiles » n'est validé à ce stade.

---

## 9. A.7 — Autonomie, cycles et conditions d'arrêt

### A.7.1. Investigation automatique — [VALIDÉ, ARBITRAGE A1]

OSIA exécute les recherches et rebonds autorisés **sans demander une validation à chaque étape**. L'utilisateur peut arrêter une investigation et intervenir sur les résultats.

Cycle fonctionnel : **analyser → évaluer → identifier les manques → prioriser → explorer → réévaluer**.

### A.7.2. Arrêt lorsque l'objectif est atteint — [VALIDÉ, ARBITRAGE A5 « OPTION D »]

Dès que le moteur considère disposer d'une réponse suffisamment étayée à l'objectif, **il arrête automatiquement l'exploration**. Il ne poursuit pas les recherches uniquement parce qu'il reste de la profondeur ou du budget.

OSIA doit ensuite :

1. produire la réponse argumentée ;
2. présenter, si elles existent, les pistes complémentaires intéressantes non explorées ;
3. **proposer** un approfondissement ;
4. attendre une **action explicite** de l'utilisateur pour poursuivre, y compris au-delà de la profondeur initialement prévue.

Toute poursuite s'effectue sous forme de **nouvelle branche** avec des limites autorisées. Autoriser davantage de profondeur n'autorise **pas** à dépasser automatiquement les plafonds financiers.

### A.7.3. Autres motifs d'arrêt — [VALIDÉ]

Le moteur doit pouvoir s'arrêter lorsque :

- aucune piste pertinente supplémentaire n'est identifiée ;
- une branche devient durablement non productive ;
- la profondeur maximale est atteinte ;
- le plafond de requêtes/branches ou le budget autorisé est atteint ;
- l'utilisateur interrompt l'investigation ;
- les sources restantes sont insuffisantes ou indisponibles.

Il doit conserver et présenter les informations déjà obtenues, même si la recherche est partielle.

### A.7.4. Deux dimensions de résultat — [VALIDÉ]

**Qualité de réponse :**

- **Réponse étayée** : réponse à la question fondée sur des éléments vérifiables ;
- **Réponse partielle** : certains aspects sont éclaircis, d'autres restent ouverts ;
- **Réponse indéterminée** : informations insuffisantes pour répondre.

**Motif de clôture :** objectif atteint, pistes épuisées, profondeur atteinte, budget atteint, interruption, sources insuffisantes, ou autre limite explicite.

La qualité de la réponse et le motif de clôture doivent rester distincts. Par exemple : « réponse partielle — budget atteint ».

---

## 10. A.8 — Gestion des contradictions et du temps

**[VALIDÉ, ARBITRAGE A6]**

Lorsque les sources divergent, OSIA doit conserver les informations contradictoires et essayer d'expliquer l'écart lorsqu'il est pertinent pour l'objectif.

Causes possibles : périodes différentes, données obsolètes, erreur de source, homonymie, divergences réellement non résolues.

Une relation peut avoir une **période de validité**. Une relation historique ne doit pas être présentée comme actuelle.

Le moteur ne doit pas :

- choisir silencieusement une seule version d'un fait contesté ;
- convertir une donnée ancienne en état présent sans vérification ;
- inventer une explication lorsqu'aucun élément ne permet de trancher ;
- déduire l'inexistence d'une relation de l'absence de résultat.

---

## 11. A.9 — Maîtrise des volumes, des coûts et des erreurs

### A.9.1. Limites cumulatives — [VALIDÉ]

L'investigation doit respecter simultanément :

- une profondeur maximale (1–10 rebonds) ;
- une limite du nombre de requêtes ;
- une limite du nombre de branches/pistes effectivement explorées ;
- un **budget maximal par investigation ou branche** ;
- un **budget global mensuel**.

Les valeurs par défaut, les unités et le barème final seront précisés ultérieurement. Le niveau **2** a été évoqué comme valeur initiale possible, sans validation définitive.

### A.9.2. Dépenses et prolongations — [VALIDÉ]

- Ne pas déclencher de recherche redondante lorsque les résultats pertinents sont déjà disponibles.
- Ne pas relancer automatiquement des API après une correction utilisateur.
- Ne pas engager de nouveaux appels lorsqu'un plafond est atteint.
- Exiger une action explicite pour attribuer des limites supplémentaires à un approfondissement.
- Distinguer les coûts estimés par l'application des montants effectivement facturés par les fournisseurs.

**Application technique :** le backend tient le budget global mensuel et les réservations transactionnelles dans PostgreSQL (B6, T3.11, T8.4). Les interfaces affichent cet état commun. Les dépenses effectuées hors de cette installation et les écarts de facturation des fournisseurs ne sont pas réputés contrôlés par ce compteur ; ils sont distingués des engagements OSIA.

### A.9.3. Résilience — [VALIDÉ]

Les cas suivants doivent être discernables : aucune donnée trouvée, source indisponible, source non configurée, résultat contradictoire, identité incertaine, recherche interrompue ou budget atteint.

L'échec d'une source ne doit pas, en lui-même, invalider tous les résultats obtenus ailleurs. Les limites correspondantes doivent apparaître dans la restitution.

---

## 12. A.10 — Restitution de la réponse

### A.10.1. Ordre de restitution — [VALIDÉ]

La présentation finale est organisée **dans cet ordre** :

1. **Réponse / synthèse IA courte**, centrée sur la question posée ;
2. **Graphe relationnel**, montrant les entités et relations découvertes ;
3. **Fiches de résultats**, regroupant les informations et les liens vers leurs sources.

### A.10.2. Contenu de la synthèse — [VALIDÉ]

La synthèse répond à l'objectif plutôt que de résumer indistinctement toutes les données collectées. Elle comporte, de manière concise :

- une réponse principale ;
- les relations ou éléments déterminants ;
- les incertitudes et contradictions significatives ;
- les limites de l'investigation et les points encore ouverts.

Les affirmations importantes doivent pouvoir être rattachées aux informations et sources présentées dans les fiches.

### A.10.3. Graphe et fiches — [VALIDÉ SUR LE PRINCIPE, DÉTAILS HORS LOT A]

Le graphe est une représentation des connaissances et relations, **pas** une preuve autonome. Il doit différencier les liens documentés, probables et simplement envisagés, ainsi que les décisions utilisateur et les relations historiques lorsque c'est pertinent.

Les fiches doivent permettre de consulter les entités, informations, justificatifs, dates et liens. Une même entité réutilisée dans plusieurs branches ne doit pas produire artificiellement plusieurs fiches identiques.

Le lot C fixe les interactions et conventions du graphe ; palette, dimensions et détails de présentation restent à concevoir dans ce cadre.

---

## 13. A.11 — Validation, rejet et approfondissement des correspondances

### A.11.1. Actions utilisateur — [VALIDÉ]

Sur une correspondance, OSIA doit proposer :

| Action | Effet fonctionnel |
|---|---|
| **Valider** | Retenir la correspondance comme hypothèse de travail ou association acceptée ; ne la transforme pas automatiquement en fait documenté |
| **Rejeter** | Exclure la correspondance des raisonnements concernés et corriger les relations qui en dépendent |
| **Approfondir** | Ouvrir une nouvelle branche chargée d'examiner plus précisément cette piste |

La décision utilisateur et le **niveau de preuve documentaire** sont deux dimensions distinctes.

### A.11.2. Deux portées de décision — [VALIDÉ]

- **Correction factuelle/d'identité** (ex. deux profils sont des homonymes) : effet sur l'ensemble de l'investigation lorsqu'il s'agit d'une même erreur d'identification.
- **Décision de pertinence** (ex. « cette piste est hors sujet pour cette branche ») : effet limité à la branche concernée.

OSIA doit éviter qu'un rejet de pertinence local efface une relation utile ailleurs.

### A.11.3. Propagation et dépenses — [VALIDÉ, ARBITRAGE A10]

Les relations qui dépendent d'une correspondance rejetée doivent être automatiquement réévaluées, sans nouvel appel API **systématique**.

Exemple : si un lien supposé entre A et B repose uniquement sur la fusion incorrecte de deux homonymes, le lien déduit ne peut plus être présenté comme valide. Les données sources d'origine restent conservées.

Si de nouvelles recherches sont nécessaires, OSIA les suggère ou les effectue uniquement dans le cadre d'une investigation explicitement relancée et autorisée.

### A.11.4. Réversibilité — [VALIDÉ]

L'utilisateur doit pouvoir revenir sur une validation ou un rejet. L'annulation déclenche une réévaluation des relations concernées à partir de l'état actuel des connaissances, sans rétablir aveuglément une ancienne conclusion.

Les décisions successives doivent rester compréhensibles et traçables.

---

## 14. A.12 — Nouvelles branches et connaissances partagées

### A.12.1. Création d'une branche — [VALIDÉ, ARBITRAGE A3 HYBRIDE]

Un approfondissement crée une **nouvelle branche dérivée**, ni une recherche totalement indépendante ni la continuation indistincte de la branche mère.

La branche :

- hérite du **contexte et des résultats pertinents** déjà collectés ;
- conserve un lien vers l'investigation et la piste d'origine ;
- peut avoir un **objectif distinct** ;
- possède ses propres limites de profondeur, de requêtes et de budget ;
- peut à son tour donner naissance à d'autres branches ;
- ne répète pas inutilement les recherches déjà effectuées.

La profondeur de la nouvelle branche se compte **depuis son propre point de départ**, sans réinitialiser la consommation globale ou les réservations déjà engagées. Le nombre de branches n'est pas soumis à une limite fonctionnelle fixe indépendante des garde-fous de volume et de consommation.

### A.12.2. Partage — [VALIDÉ, ARBITRAGE A9]

| Élément | Partage entre branches |
|---|---|
| Informations collectées et sourcées | Oui, socle de connaissances commun |
| Hypothèses et relations | Réutilisables avec leurs réserves et preuves |
| Décisions factuelles d'identification | Propagées lorsqu'elles sont applicables à toutes les branches |
| Décisions de pertinence | Restent propres à la branche |
| Objectifs, progression et conclusions | Propres à chaque branche |

Une découverte dans une branche peut enrichir les connaissances de l'investigation principale **sans modifier silencieusement sa synthèse**.

### A.12.3. Réutilisation des recherches antérieures — [VALIDÉ]

- Réutiliser une information déjà collectée si elle reste adaptée à l'objectif.
- Vérifier à nouveau une donnée potentiellement périmée lorsque c'est justifié.
- Conserver la date de collecte et, si disponible, la date de validité des faits.
- Ne pas appliquer à toutes les sources un même délai arbitraire de fraîcheur.

### A.12.4. Consommation propre à la branche — [VALIDÉ]

La création d'une branche ne consomme pas de crédit en elle-même. Le lancement d'un approfondissement nécessite des limites autorisées pour cette branche, qui restent cumulatives avec le plafond mensuel global.

---

## 15. A.13 — Révision des conclusions et lecture multibranche

### A.13.1. Conclusion devenue obsolète — [VALIDÉ, ARBITRAGE A11]

Une découverte ou une correction peut remettre en cause une conclusion passée. OSIA doit :

1. conserver les informations et sources contradictoires ;
2. réévaluer les relations dépendantes ;
3. **signaler** qu'une synthèse existante n'est plus entièrement à jour ;
4. proposer l'**actualisation de la synthèse sur demande** ;
5. conserver la traçabilité de la révision, sans réécrire silencieusement l'historique.

Les réévaluations ne doivent pas entraîner une nouvelle consommation API automatique et incontrôlée.

### A.13.2. Graphe commun filtrable — [VALIDÉ, ARBITRAGE A12]

L'investigation comporte **un graphe relationnel commun** à l'ensemble des branches, avec possibilité de **filtrer par branche**.

Chaque branche dispose de son objectif et de sa synthèse. Les fiches d'entités restent communes et indiquent, lorsque c'est utile, dans quelles branches l'entité intervient.

Une nouvelle découverte peut être signalée comme pertinente pour une branche déjà terminée ; cela **ne relance pas automatiquement** celle-ci.

### A.13.3. Historique des décisions — [VALIDÉ]

La session doit permettre de comprendre les validations, rejets, annulations et révisions de conclusion. L'objectif est la **compréhensibilité** des changements, pas un système d'audit complexe.

---

## 16. Contexte produit et interfaces avec les autres lots

Les éléments ci-dessous ont été décidés au niveau du projet, mais **leur conception détaillée ne fait pas partie du lot A**.

| Sujet | Décision ou orientation retenue | Périmètre |
|---|---|---|
| Interface | **Une page unique**, indices et objectif en haut, résultats en dessous | Interface |
| Comptes | Aucun compte cloud OSIA imposé ; pas de gestion collaborative requise en V1. Authentification et autorisations obligatoires en mode serveur selon T5.7 | Produit / sécurité |
| Paramètres | **Un seul menu** ouvrant une grande modale regroupant options et configuration | Interface |
| Fournisseur IA | **Mistral ou autre fournisseur/modèle configurable** ; pas de dépendance fonctionnelle exclusive | Configuration / technique |
| Sources | Toutes activées par défaut si disponibles, désactivables individuellement | Sources / connecteurs |
| Stockage | **Backend et PostgreSQL** pour les données structurées ; preuves et binaires dans un stockage de fichiers dédié (T2). Le navigateur ne porte pas l'état métier faisant autorité | Données / technique |
| Persistance, export, sauvegarde | Enregistrement local progressif ; export portable manuel ; sauvegarde technique manuelle et programmation facultative (D1, D5, T2.5–T2.6, T7.9) | Données / export |
| Consultation locale | Export sous forme de **page HTML autonome**, avec synthèse, graphe et fiches consultables localement, sans exposer les clés API | Export |
| Confidentialité | Approche légère et pragmatique, mais protection des clés et visibilité sur les données envoyées aux fournisseurs | Sécurité / données |
| Réactualisation des recherches anciennes | Surveillance automatisée dans le temps : piste V2. La reprise après incident et la consultation des archives sont distinctes et régies par D7/T3/T4/T7 | Roadmap / résilience |

**Précision consolidée :** les premières pistes de stockage métier dans le navigateur sont remplacées par T2/T3. Le moteur assure la persistance, les appels externes et les politiques. Les éventuelles préférences d'affichage locales du frontend ne constituent ni une base métier de référence ni un contrôle de budget.

**Export HTML :** l'objectif est une consultation locale des résultats enregistrés ; l'export n'a pas vocation à embarquer des clés API ni à poursuivre automatiquement des recherches hors ligne.

---

## 17. Règles transversales impératives

1. **L'objectif n'est pas un fait.** Une formulation orientée doit être reformulée en hypothèse vérifiable.
2. **Une information n'est pas une relation.** Une adresse commune ne suffit pas à prouver un groupe commun.
3. **Une identité probable n'est pas une identité confirmée.** Les homonymes doivent pouvoir rester distincts.
4. **La confiance n'est pas la pertinence.** Le moteur doit évaluer séparément ces dimensions.
5. **Une validation utilisateur n'est pas une preuve documentaire.** Les sources restent nécessaires.
6. **Une source absente ou indisponible n'est pas une preuve d'inexistence.** Les limites de couverture sont indiquées.
7. **Une information datée ne doit pas devenir un fait actuel par défaut.** Les relations historiques sont qualifiées.
8. **Les données sourcées ne sont pas effacées par un rejet de correspondance.** Les associations et conclusions déduites sont corrigées.
9. **Une branche ne duplique pas aveuglément les recherches.** Les résultats existants sont réutilisés lorsqu'ils sont toujours pertinents.
10. **Aucune poursuite au-delà des limites n'est automatique.** Une nouvelle branche et une autorisation explicite sont nécessaires.
11. **Les conclusions ne sont pas modifiées silencieusement.** Une synthèse devenue obsolète est signalée.
12. **Une recherche terminée peut être partielle.** Le motif d'arrêt et la qualité de réponse sont affichés séparément.

---

## 18. Scénarios fonctionnels de référence (critères d'acceptation)

Ces scénarios sont destinés à vérifier le comportement attendu lors d'une future recette fonctionnelle. Ils ne préjugent ni de la solution technique ni des données concrètes des sources.

### S01 — Objectif explicite et sous-questions

**Étant donné** une adresse et l'objectif « identifier les liens entre les entreprises présentes », **lorsque** la recherche démarre, **alors** OSIA doit examiner les entités pertinentes, leurs liens documentés et les informations manquantes, sans présenter une simple liste d'entreprises comme une réponse complète.

### S02 — Objectif biaisé

**Étant donné** « prouver que A contrôle B », **lorsque** les sources ne suffisent pas à établir cette relation, **alors** OSIA doit l'indiquer et ne pas inventer de preuve.

### S03 — Décompte des rebonds

**Étant donné** une profondeur de 2, **lorsque** plusieurs sources sont interrogées au niveau 1, **alors** ces appels ne doivent pas être comptés comme autant de rebonds distincts.

### S04 — Sources désactivées

**Étant donné** une source désactivée, **lorsque** l'investigation choisit ses recherches, **alors** cette source n'est jamais interrogée, même si elle serait pertinente.

### S05 — Homonymes

**Étant donné** deux personnes de même nom sans preuve qu'il s'agit de la même, **lorsque** OSIA analyse leurs profils, **alors** elle doit conserver l'incertitude et éviter de créer artificiellement des relations via une fusion non établie.

### S06 — Rejet et propagation

**Étant donné** un lien A–B déduit uniquement d'une identification erronée, **lorsque** l'utilisateur rejette cette identification, **alors** les relations dépendantes sont réévaluées, les sources originales sont conservées et aucun appel API nouveau n'est systématiquement lancé.

### S07 — Rejet local de pertinence

**Étant donné** une piste jugée hors sujet dans la branche 1, **lorsque** l'utilisateur la rejette pour cette raison, **alors** elle peut rester disponible pour la branche 2 si elle y est pertinente.

### S08 — Réponse trouvée avant la limite

**Étant donné** une profondeur maximale de 5 et une réponse étayée au niveau 2, **lorsque** l'objectif est atteint, **alors** OSIA s'arrête et suggère, le cas échéant, des pistes complémentaires sans les lancer seule.

### S09 — Prolongation au-delà de la profondeur initiale

**Étant donné** une investigation terminée et une piste proposée, **lorsque** l'utilisateur choisit de l'approfondir, **alors** OSIA ouvre une branche liée, reprend les informations utiles et applique de nouvelles limites explicitement autorisées.

### S10 — Budget atteint

**Étant donné** un plafond de consommation atteint, **lorsque** le moteur devrait lancer une nouvelle recherche, **alors** il ne la lance pas, conserve les acquis et mentionne « budget atteint » comme motif d'arrêt.

### S11 — Sources contradictoires dans le temps

**Étant donné** deux sources présentant des dirigeants différents à des dates distinctes, **lorsque** OSIA compare les informations, **alors** elle vérifie si la différence reflète une succession historique avant de qualifier les données de contradictoires.

### S12 — Découverte d'une branche et synthèse mère

**Étant donné** une branche secondaire qui découvre un fait remettant en question la synthèse principale, **lorsque** ce fait est intégré aux connaissances communes, **alors** la synthèse principale est signalée comme nécessitant une actualisation, sans réécriture silencieuse.

### S13 — Investigation interrompue

**Étant donné** une recherche arrêtée par l'utilisateur ou une source en échec, **lorsque** les résultats sont affichés, **alors** la qualité de réponse et la raison de l'arrêt sont indiquées distinctement ; les informations obtenues restent consultables.

### S14 — Pistes secondaires

**Étant donné** une piste non prioritaire découverte au cours de la recherche, **lorsque** OSIA décide de ne pas l'explorer, **alors** elle est conservée avec son statut, et peut être proposée pour approfondissement manuel.

### S15 — Investigation à plusieurs sous-objectifs

**Étant donné** une phrase demandant des liens présents et historiques, **lorsque** OSIA conclut, **alors** elle doit distinguer ce qui est établi pour chacun de ces aspects et ne pas confondre relations anciennes et actuelles.

---

## 19. Registre des arbitrages validés

| Référence | Sujet | Décision actée |
|---|---|---|
| **A1** | Mode d'exécution | **Option A :** investigation automatique, sans validation à chaque rebond |
| **A2** | Pistes secondaires | **Option B :** conserver sans approfondir automatiquement |
| **A3** | Approfondissement | **Hybride A/B :** nouvelle branche rattachée à l'investigation, héritant des résultats et du contexte |
| **A4** | Prise en compte de l'objectif | **Option B :** priorité à l'objectif, découverte périphérique permise |
| **A5** | Objectif atteint avant la limite | **Option D :** arrêt automatique + suggestions d'approfondissement, poursuite uniquement sur décision utilisateur |
| **A6** | Sources contradictoires | Conserver les versions et examiner leurs écarts, notamment temporels |
| **A7** | Plan d'investigation | Dynamique, sans validation intermédiaire obligatoire |
| **A8** | Sous-objectifs | Plusieurs sous-objectifs compris depuis une phrase unique |
| **A9** | Partage interbranches | Données sourcées communes ; objectifs et conclusions indépendants |
| **A10** | Corrections | Propagation automatique des impacts, sans appel API systématique |
| **A11** | Conclusions devenues obsolètes | Signalement + actualisation de la synthèse sur demande |
| **A12** | Graphe multibranche | Graphe commun avec filtres par branche |

**Attention à la numérotation :** les références **A1 à A12** ci-dessus désignent les **arbitrages**. Les sections de cadrage **A.1 à A.13** désignent les **thèmes fonctionnels** ; ce sont deux nomenclatures distinctes.

---

## 20. Points volontairement non figés

Les points ci-dessous indiquent les détails à spécifier. Leurs principes sont désormais encadrés par B–D et T1–T8 ; seul le détail non fixé subsiste. Voir [conception restante](../CONCEPTION-RESTANTE.md).

1. **Valeurs par défaut et plafonds exacts** : profondeur initiale, nombre de requêtes, nombre de branches, budget proposé, unités et règles de réinitialisation mensuelle.
2. **Seuil de réponse « suffisamment étayée »** : critères et méthode d'évaluation, sans réduction à un score arbitraire.
3. **Jauge de confiance** : mode de calcul et présentation graphique.
4. **Catalogue final des sources et connecteurs** : couverture géographique, capacités, disponibilité, accès et coût.
5. **Éventuelles confirmations exceptionnelles** en cas de demande trop ambiguë ou d'objectif inexploitable : comportement détaillé à préciser sans imposer de validation systématique.
6. **Gestion de la fraîcheur** : quand réinterroger une donnée déjà collectée.
7. **Granularité de l'historique** : niveau de détail conservé pour corrections, révisions et consommation.
8. **Fonctionnement concret du graphe** : filtres, lisibilité, exploration, interaction et jauges.
9. **Mécanismes de stockage et d'export** : formats internes, reprise d'une session, autonomie exacte de l'HTML exporté et gestion des données sensibles.
10. **Application des budgets** : suivi et estimation des prix API, coûts imprévus, plafonds propres au fournisseur et limites du suivi local.
11. **Aspects légaux et protection des données** : périmètre public assumé, conditions d'utilisation des sources, minimisation des données personnelles et protection des secrets.

### Hors V1 acté

La **réactualisation automatisée d'une ancienne investigation** (surveillance des changements au fil des mois) est prévue comme une piste de **V2**, et n'est pas une obligation de ce lot.

---

## 21. Critère de complétude du lot A

Le cadrage fonctionnel du lot A est considéré comme **consolidé** lorsque les décisions ci-dessus servent de référence pour les lots suivants. Il n'exige pas que les seuils, les fournisseurs d'API, les composants techniques ou la maquette graphique soient déjà arrêtés.

**Résultat fonctionnel attendu du moteur :** à partir d'indices et d'un objectif éventuel, OSIA doit conduire une investigation automatique bornée, explorer les relations pertinentes, gérer les incertitudes, produire une réponse documentée, puis permettre à l'utilisateur de corriger et d'approfondir les pistes sous forme de branches liées — sans perte des sources ni dépenses incontrôlées.

---

*Fin du lot A — édition consolidée 1.1.*
