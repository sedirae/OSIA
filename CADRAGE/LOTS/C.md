# OSIA — Cadrage fonctionnel — Lot C : Interface et restitution

> **Édition consolidée : 1.1 — 06/11/2026.** Les arbitrages conservent leur validation initiale. Cette édition harmonise les formulations avec les lots ultérieurs ; elle ne vaut pas attestation de développement. Références : [index](../README.md), [résolutions de cohérence](../AUDIT-COHERENCE.md), [registre des décisions](../../COWORKAI/DECISIONS.md).


> **Version :** 1.1  
> **Statut :** VALIDÉ — lot clôturé  
> **Date de validation :** 05/11/2026  
> **Projet :** OSIA — outil d'investigation OSINT assistée par IA  
> **Objet :** cadrer l'expérience utilisateur, le suivi des investigations, l'exploration des relations, la vérification des résultats et leur restitution.  
> **Arbitrages :** C1 à C7, tous validés en **option C**.

---

## 1. Objet du document

Ce document consolide les **décisions fonctionnelles validées** du lot C. Il est destiné à être lisible par une personne et directement exploitable par une IA chargée du cadrage technique, de la conception ou du développement.

Il s'appuie sur les principes actés dans les lots précédents :

- **Lot A — Cadrage fonctionnel :** investigations à partir d'objectifs et d'indices, progression autonome bornée, arrêt automatique lorsque la réponse est suffisamment étayée, prolongations volontaires sous forme de branches, maîtrise des plafonds et des dépenses, exports portables manuels ; persistance et sauvegardes techniques selon D/T2.
- **Lot B — Sources et connecteurs :** sélection et consultation de sources OSINT selon les capacités autorisées ; traçabilité, explicabilité et distinction des informations issues des sources et des interprétations de l'IA.
- **Lot C — Interface et restitution (ce document) :** présentation et interactions de l'utilisateur avec ces fonctions et leurs résultats.
- **Lot D — Paramètres et données locales (validé) :** réglages persistants, modalités de conservation, formats de fichiers, gestion des données locales et détails techniques associés.

### 1.1 Périmètre

Sont inclus :

1. L'organisation de l'interface web.
2. La saisie et le suivi d'une investigation.
3. La synthèse IA et ses liens avec les preuves.
4. Le graphe relationnel et ses modes d'exploration.
5. Les fiches des entités, relations et sources associées.
6. La validation, le rejet, la correction et la traçabilité des interventions humaines.
7. Les branches d'approfondissement, les vues consolidées et la restitution dans l'interface.

Sont **hors périmètre de décision de ce lot** : choix de framework et bibliothèques, schémas de stockage définitifs, politiques de rétention, formats d'export précis, mécanismes de persistance et stratégies de gestion des secrets/API. Les principes de ces sujets sont désormais fixés par D et T1–T8 ; seuls leurs détails non arbitrés restent à concevoir.

### 1.2 Portée normative

Pour éviter toute ambiguïté :

- **EXIGENCE VALIDÉE :** comportement décidé au titre du lot C et à respecter.
- **MODALITÉ À PRÉCISER :** détail d'implémentation ou d'ergonomie non arbitré ; ne pas le présenter comme une décision définitive.
- **PRINCIPE HÉRITÉ :** contrainte issue des lots A/B, rappelée ici sans la modifier.

Les illustrations et exemples d'entreprise, de personne ou d'adresse sont fictifs et non prescriptifs.

---

## 2. Synthèse des arbitrages

| Référence | Intitulé | Choix validé | Résumé |
|---|---|---|---|
| **C1** | Organisation générale de l'interface | **Option C** | Interface web **hybride et contextuelle** sur une page, avec synthèse et graphe centraux, panneaux secondaires ouverts à la demande. |
| **C2** | Saisie et suivi d'une investigation | **Option C** | **Saisie rapide et suivi dynamique**, avec paramètres avancés repliables et suivi des opérations et consommations réellement constatées. |
| **C3** | Synthèse IA et conclusions | **Option C** | **Synthèse évolutive, structurée et interactive**, reliée aux entités, relations et sources ; distinguant faits, hypothèses, contradictions et limites. |
| **C4** | Graphe relationnel | **Option C** | **Graphe adaptatif, sémantique et exploratoire** : modes réseau, arborescent et regroupé, filtres, exploration progressive et conventions de représentation des relations. |
| **C5** | Fiches d'entités et de relations | **Option C** | **Fiches contextuelles enrichies et traçables**, avec provenance au niveau des informations, sections détaillées et historique. |
| **C6** | Validation et correction | **Option C** | **Validation supervisée, non destructive et réversible** ; distinction entre étayage documentaire et décision de l'utilisateur. |
| **C7** | Navigation, branches et restitution | **Option C** | **Espace d'investigation unifié et navigation multi-branches**, vues par branche et consolidée, rapports consultables et exports déclenchés manuellement. |

**Statut des sept arbitrages : validés. Aucun arbitrage C restant ouvert.**

---

## 3. Principes transversaux

### 3.1 Une seule page, plusieurs niveaux de lecture

L'utilisateur doit pouvoir :

- lancer une investigation sans parcourir un assistant en plusieurs écrans ;
- comprendre rapidement sa progression et ses principales conclusions ;
- passer d'une conclusion à sa relation, puis à l'entité et aux sources qui la justifient ;
- revenir au graphe sans perdre le contexte ;
- consulter l'historique et les branches sans confondre ces éléments avec des relations factuelles.

Le parcours général suit la logique **saisie → suivi → synthèse → graphe → fiches/preuves → vérification → approfondissement éventuel → restitution**, sans imposer cet ordre comme navigation obligatoire.

### 3.2 Trois couches d'information distinctes

L'interface doit préserver explicitement la séparation entre :

1. **Les données issues des sources** : observations, identifiants, documents, déclarations et leur provenance.
2. **Les traitements et interprétations de l'IA** : extraction, normalisation, rapprochements et hypothèses, assortis de leur justification.
3. **Les interventions de l'utilisateur** : acceptation, rejet, correction, annotation, rapprochement, fusion/séparation ou annulation d'une décision.

Une correction humaine ne transforme pas automatiquement une hypothèse en preuve documentaire ; une information provenant d'une source ne devient pas nécessairement une conclusion fiable sans examen.

### 3.3 Traçabilité et absence de modification destructive

Les opérations d'exploration, de correction et de restitution ne doivent pas supprimer silencieusement les éléments qui ont conduit à une conclusion. Les sources initiales, propositions d'origine, décisions et versions pertinentes doivent rester identifiables dans le périmètre de l'investigation.

### 3.4 Maîtrise explicite des ressources

Les interactions d'interface ne doivent pas provoquer un dépassement des limites autorisées : profondeur, nombre de recherches, branches et budget, notamment pour les appels API payants.

**PRINCIPE HÉRITÉ :** la poursuite d'une investigation après son arrêt n'est **jamais automatique**. Elle requiert une action explicite, avec nouvelles limites de branche clairement définies et acceptées.

---

## 4. C1 — Interface hybride et contextuelle

### Décision

**EXIGENCE VALIDÉE :** une interface web **sur une page**, centrée sur la synthèse et le graphe, avec panneaux contextuels accessibles à la demande.

### Règles fonctionnelles

- **C1-01** — La page principale intègre la saisie/recherche, le suivi, la synthèse et l'accès au graphe relationnel ; l'organisation peut s'adapter à l'état de l'investigation.
- **C1-02** — Les fiches d'entités, relations, sources, paramètres ou autres détails sont ouvertes dans des panneaux contextuels plutôt que de provoquer un changement de page systématique.
- **C1-03** — Ouvrir ou fermer un panneau ne doit pas faire perdre la sélection, le contexte ou la position du graphe.
- **C1-04** — Sur ordinateur, les panneaux doivent pouvoir être **fermés, redimensionnés ou épinglés** lorsque cela a du sens.
- **C1-05** — L'interface est **responsive** : la consultation et les interactions essentielles restent possibles sur de petits écrans, avec une présentation adaptée des panneaux.
- **C1-06** — L'utilisateur doit pouvoir revenir rapidement à la vue d'ensemble.

### Détails non figés

Largeurs exactes, points de rupture, architecture des composants, animations, palette graphique et disposition pixel par pixel sont **à préciser** lors de la conception UI.

---

## 5. C2 — Saisie rapide et suivi dynamique

### Décision

**EXIGENCE VALIDÉE :** une saisie directe de l'investigation ; les paramètres avancés sont repliables ; le lancement transforme le même espace en surface de suivi dynamique.

### Saisie initiale

- **C2-01** — La saisie principale accueille l'**objectif facultatif** de recherche en langage naturel. Sans objectif, les indices lancent une investigation exploratoire (A.1).
- **C2-02** — L'utilisateur peut fournir **plusieurs indices de départ** : noms, organisations, adresses, identifiants ou autres éléments pertinents.
- **C2-03** — Les paramètres de sources, profondeur, plafonds/budget, nombre de recherches et nombre de branches sont accessibles dans une section **avancée repliable**.
- **C2-04** — Les sources sont activées ou désactivées selon les mécanismes prévus par les lots antérieurs ; les paramètres avancés ne doivent pas occulter les plafonds applicables.
- **C2-05** — Un lancement nécessite une configuration admissible au regard des limites globales et de l'investigation.

### Suivi de l'exécution

- **C2-06** — Après lancement, un état synthétique indique notamment le statut de l'investigation, les entités/relations découvertes, la profondeur atteinte et la consommation de ressources.
- **C2-07** — Un journal détaillé expose, autant que les sources le permettent, les opérations réalisées : consultations, recherches, décisions, nouveaux liens, erreurs et rejets.
- **C2-08** — Les branches et rebonds identifiés sont visibles sans masquer l'objectif et les indices initiaux.
- **C2-09** — La consommation affichée doit correspondre aux mesures réellement disponibles et distinguer, lorsque nécessaire, engagé, estimé et restant ; aucun montant exact ne doit être fabriqué.
- **C2-10** — Ne pas utiliser de **pourcentage de progression artificiel** pour une investigation exploratoire dont la complétion ne peut pas être mesurée de façon fiable.
- **C2-11** — L'utilisateur peut arrêter une investigation, consulter ses résultats intermédiaires et déclencher une sauvegarde manuelle.
- **C2-12** — En cas de limite atteinte ou d'arrêt anticipé, l'interface présente les résultats partiels et indique clairement la cause de l'arrêt.

### États de suivi à représenter

Il faut au minimum distinguer une investigation **non lancée**, **en cours**, **terminée avec réponse suffisamment étayée**, **arrêtée sur limite**, **arrêtée par l'utilisateur** et **en erreur**. Les libellés précis et les éventuels sous-états techniques pourront être définis ensuite.

---

## 6. C3 — Synthèse IA évolutive, structurée et interactive

### Décision

**EXIGENCE VALIDÉE :** une synthèse courte, intelligible, régulièrement mise à jour lorsque les découvertes sont significatives et directement navigable vers les preuves.

### Structure de la synthèse

- **C3-01** — Une **réponse narrative concise** apparaît en tête de synthèse ; elle répond à la question initiale, y compris lorsque la réponse reste négative ou partielle.
- **C3-02** — La synthèse distingue les **faits documentés**, les **hypothèses**, les **incertitudes/contradictions**, les **limites** et les **pistes d'approfondissement** pertinentes.
- **C3-03** — Les conclusions importantes comportent des renvois utilisables vers les entités, relations et sources qui les étayent.
- **C3-04** — Pendant la recherche, la synthèse porte un statut **provisoire** ; elle ne doit pas être entièrement régénérée à chaque consultation de source si aucune découverte significative ne le justifie.
- **C3-05** — À l'arrêt ou à la clôture de l'investigation, une synthèse **stabilisée** restitue les résultats disponibles et leurs limites.
- **C3-06** — Une correction humaine ou une nouvelle branche peut rendre une synthèse stabilisée obsolète : signaler cet état et actualiser cette synthèse sur demande (A11). Pendant une investigation active, les mises à jour de la synthèse provisoire restent autorisées sous les budgets existants. Les versions pertinentes restent retraçables.

### Qualification des assertions

| Qualification | Interprétation à afficher |
|---|---|
| **Documenté** | Appuyé par une ou plusieurs sources identifiables, sans prétendre garantir à lui seul l'exactitude. |
| **Corroboré** | Plusieurs éléments suffisamment indépendants concordent. |
| **À confirmer** | Des indices existent, mais la démonstration reste insuffisante. |
| **Contradictoire** | Des sources ou constats incompatibles restent à expliquer. |
| **Non établi** | Les éléments disponibles ne suffisent pas pour soutenir la proposition. |

- **C3-07** — Ne pas afficher de **score de fiabilité chiffré** (par exemple « 94 % ») sans modèle de calibration réellement défendable.
- **C3-08** — Les qualifications expriment l'**étayage**, et non une probabilité mathématique de vérité.
- **C3-09** — Toute conclusion substantielle doit pouvoir être reliée à des éléments vérifiables ou être clairement désignée comme une interprétation/hypothèse de l'IA.

---

## 7. C4 — Graphe adaptatif, sémantique et exploratoire

### Décision

**EXIGENCE VALIDÉE :** un graphe interactif capable de présenter aussi bien des investigations modestes que des réseaux étendus, en donnant à l'utilisateur la maîtrise de ce qu'il voit.

### Interactions

- **C4-01** — Zoom et déplacement libres dans le graphe.
- **C4-02** — Sélection d'un **nœud** ouvrant sa fiche contextuelle.
- **C4-03** — Sélection d'une **relation** ouvrant son type, son statut et ses sources.
- **C4-04** — Exploration progressive des branches et voisins masqués, sans obligation d'afficher tout le réseau simultanément.
- **C4-05** — Recherche et mise en évidence d'une entité dans le graphe.
- **C4-06** — Filtres visuels par type d'entité, relation, statut, profondeur ou critères pertinents.
- **C4-07** — Déplacement manuel et **fixation** de nœuds ; conservation de leur position à l'échelle de la session et, selon les décisions du lot D, au-delà.

### Modes de représentation

- **C4-08 — Réseau :** représentation libre des connexions factuelles ou hypothétiques entre entités.
- **C4-09 — Arborescent :** représentation des **chemins et rebonds d'exploration** ; cette arborescence ne doit pas être prise pour une hiérarchie réelle entre les entités.
- **C4-10 — Regroupé :** regroupement visuel par catégories ou communautés, pour maintenir la lisibilité.
- **C4-11** — Les groupes doivent pouvoir être repliés/dépliés, avec indication du nombre d'éléments masqués lorsque cela est pertinent.
- **C4-12** — Les regroupements et filtres sont **purement visuels** : ils ne créent pas, ne valident pas et ne suppriment pas de faits ou relations.
- **C4-13** — Il doit rester possible de distinguer un élément **masqué** d'un élément **absent** des résultats.

### Sémantique visuelle

- **C4-14** — Les catégories d'entités sont distinguées par des conventions visuelles cohérentes, notamment par leur couleur et/ou leur forme.
- **C4-15** — Les liens **documentés** sont représentés par une ligne continue et les liens **hypothétiques** par une ligne discontinue ; les **contradictions** disposent d'un marquage distinct.
- **C4-16** — Les relations rejetées peuvent être masquées dans la vue courante, mais demeurent consultables dans l'historique.
- **C4-17** — L'interface ne doit pas donner graphiquement à une hypothèse l'apparence d'un fait confirmé.

### Performance et grande volumétrie

La représentation doit rester exploitable avec **plusieurs centaines d'entités**, en utilisant au besoin l'affichage progressif et les regroupements. Aucun seuil fixe ou technologie de rendu n'est imposé dans le présent lot.

---

## 8. C5 — Fiches contextuelles enrichies et traçables

### Décision

**EXIGENCE VALIDÉE :** une fiche contextuelle donne un aperçu immédiat de l'objet sélectionné, puis des sections détaillées ouvrables à la demande ; la provenance des informations est explicite.

### Fiche d'entité

- **C5-01** — Présenter identité, type, caractéristiques, identifiants utiles et alias/dénominations alternatives lorsqu'ils existent.
- **C5-02** — Afficher ses relations entrantes et sortantes et permettre la navigation vers les objets liés.
- **C5-03** — Associer les informations importantes à leur(s) source(s) propre(s), et non uniquement à une bibliographie générale de la fiche.
- **C5-04** — Afficher les dates pertinentes : collecte, publication, et date/période de validité lorsque connues.
- **C5-05** — Proposer des sections repliables pour les preuves, l'historique et les autres détails.

### Fiche de relation

- **C5-06** — Présenter les entités concernées, la nature du lien, sa direction si nécessaire et sa période de validité lorsqu'elle est connue.
- **C5-07** — Présenter les justifications, les sources et le statut d'étayage de la relation.
- **C5-08** — Permettre de naviguer vers les fiches des entités associées sans perdre le contexte du graphe.

### Qualité et identité

- **C5-09** — Distinguer clairement une donnée présente dans une source d'une **déduction de l'IA**.
- **C5-10** — Ne pas fusionner deux personnes ou organisations sur la seule base d'un nom similaire.
- **C5-11** — Les rapprochements ambigus doivent demeurer identifiables comme propositions ; leur fusion nécessite une justification et une validation humaine.
- **C5-12** — Les mécanismes de fusion ou séparation doivent préserver les éléments d'origine et leur traçabilité.
- **C5-13** — Distinguer l'**historique factuel** de l'entité (changement d'adresse, ancien dirigeant, etc.) de l'**historique des opérations dans OSIA**.

Les entités ne sont pas limitées aux entreprises et personnes : adresses, domaines, documents et autres catégories pertinentes sont admis selon les sources/connecteurs et le modèle métier.

---

## 9. C6 — Validation supervisée, non destructive et réversible

### Décision

**EXIGENCE VALIDÉE :** l'utilisateur peut examiner et intervenir sur les propositions de l'IA sans détruire les données initiales ; les décisions et corrections sont réversibles et historisées.

### Actions

- **C6-01 — Valider :** accepter une proposition dans l'espace de travail.
- **C6-02 — Rejeter :** écarter une proposition des conclusions retenues sans effacer les éléments initiaux.
- **C6-03 — Corriger :** créer une version corrigée d'une information, de la caractérisation d'une entité ou d'une relation.
- **C6-04 — Annoter :** ajouter un commentaire ou une réserve.
- **C6-05 — Rapprocher :** proposer une correspondance possible entre entités.
- **C6-06 — Fusionner / séparer :** confirmer ou annuler un regroupement d'entités, en conservant leur provenance.
- **C6-07 — Annuler une décision :** inverser la décision via une nouvelle opération traçable et réévaluer les conséquences avec les connaissances actuelles ; ne pas rétablir aveuglément une ancienne conclusion (A.11.4).
- **C6-08** — Les actions peuvent viser une entité, une relation ou une information individuelle lorsque cela est pertinent.

### Deux dimensions de statut indépendantes

**Statut d'étayage documentaire** : documenté, corroboré, à confirmer, contradictoire ou non établi.

**Statut de décision humaine** : non examiné, validé ou rejeté.

- **C6-09** — Une proposition « à confirmer » peut être « validée » par l'utilisateur **sans devenir une preuve établie**.
- **C6-10** — Un fait documenté peut être contesté ou rejeté dans l'analyse, tout en préservant le document source.

### Journal des interventions

- **C6-11** — Chaque opération garde la cible et la version concernées, l'action effectuée, sa date/heure, la valeur corrigée éventuelle et ses effets.
- **C6-12** — Une justification peut être fournie par l'utilisateur, mais n'est pas imposée pour toute action.
- **C6-13** — Les actions humaines sont distinguées des opérations automatisées de l'IA ; cette distinction n'impose pas de gestion collaborative de comptes. L'authentification et les autorisations du mode serveur restent obligatoires (T5.7).
- **C6-14** — La réversibilité ne consiste pas à effacer le passé : une annulation constitue elle-même une opération historisée.

### Effets sur l'investigation

- **C6-15** — Une correction actualise les vues dérivées et réévalue les dépendances. Une synthèse stabilisée touchée est signalée comme à actualiser ; sa régénération est demandée explicitement (A11, C3-06). Les originaux et versions conservées restent intacts.
- **C6-16** — Lorsqu'une correction invalide une branche active, l'interface doit refléter la nécessité éventuelle d'une réévaluation ou d'un arrêt de cette branche.
- **C6-17** — Les recherches déjà effectuées restent historisées, même si la proposition qui les avait motivées est rejetée.
- **C6-18** — Aucune réanalyse IA payante ne doit faire dépasser les limites ou budgets autorisés sans nouvel accord explicite.
- **C6-19** — Les décisions humaines ne doivent pas exiger l'interruption systématique de l'investigation autonome en cours.

---

## 10. C7 — Espace unifié, branches et restitution finale

### Décision

**EXIGENCE VALIDÉE :** chaque investigation possède un espace de travail unifié ; ses approfondissements sont des branches identifiables, tandis que les vues et rapports peuvent porter sur une branche ou sur un ensemble consolidé.

### Deux structures à ne pas confondre

| Structure | Représente | Ne représente pas automatiquement |
|---|---|---|
| **Graphe relationnel** | Entités et liens découverts ou proposés | L'ordre chronologique de la recherche |
| **Arbre des investigations** | Investigation principale, approfondissements, origine et limites des branches | Des relations factuelles entre entreprises, personnes ou objets |

- **C7-01** — L'utilisateur peut naviguer dans l'arbre des investigations et sélectionner une branche sans perdre l'accès au graphe relationnel.
- **C7-02** — Chaque branche présente son objectif, son contexte hérité, son état, son journal, ses découvertes et sa consommation propre.
- **C7-03** — Les chemins ayant abouti à une même découverte restent retraçables, y compris lorsqu'une entité est dédupliquée dans la vue consolidée.

### Approfondissements

- **C7-04** — À l'arrêt de l'investigation, les pistes supplémentaires pertinentes peuvent être proposées, avec leur objectif et leur justification.
- **C7-05** — Une piste est **suggérée mais non exécutée** tant que l'utilisateur ne confirme pas son lancement.
- **C7-06** — Le lancement explicite d'une branche présente ses paramètres et ses limites propres, hérités ou modifiés dans le respect des plafonds globaux.
- **C7-07** — Une nouvelle branche réutilise le contexte et les résultats déjà collectés lorsque possible, sans reproduire systématiquement les appels aux sources.
- **C7-08** — Une branche possède son propre état et journal ; son lien avec l'investigation d'origine reste visible.

### Vue consolidée

- **C7-09** — L'utilisateur peut afficher les résultats d'une branche sélectionnée ou d'un ensemble de branches dans une **vue consolidée**.
- **C7-10** — Les entités clairement identifiées comme identiques ne doivent pas être dupliquées artificiellement.
- **C7-11** — Une même information reproduite sur plusieurs sites ne doit pas être considérée automatiquement comme plusieurs preuves indépendantes lorsque l'origine est commune.
- **C7-12** — Les contradictions entre branches sont conservées et signalées, même lorsqu'une interprétation a été retenue par l'utilisateur.
- **C7-13** — La consolidation ne modifie ni n'efface les historiques des branches d'origine.

### Restitution consultable

- **C7-14 — Rapport synthétique :** objectif, réponse principale, faits et conclusions majeurs, sources principales, limites.
- **C7-15 — Dossier détaillé :** entités, relations, preuves et provenance, contradictions, interventions humaines, historique des branches concernées.
- **C7-16** — Les rapports sont consultables dans l'interface **avant tout export**.
- **C7-17** — L'utilisateur choisit la portée de la restitution : investigation/branche spécifique ou résultats consolidés ; le périmètre sélectionné est clairement indiqué.
- **C7-18** — Les **exports portables** sont manuels et ne sont jamais déclenchés automatiquement à la clôture. L'enregistrement progressif est automatique (D1). La sauvegarde technique manuelle ou programmée facultativement suit T2 ; elle ne se confond pas avec l'export (T7.9).
- **C7-19** — Les restitutions préservent la séparation entre sources, affirmations, hypothèses et décisions humaines.
- **C7-20** — Une nouvelle exploration peut produire une **version actualisée** du rapport, sans modifier silencieusement les versions déjà explicitement conservées.

**Complété par D, T2 et T7 :** archives `.osia`, HTML autonome, conservation, paramètres, sauvegarde technique et restauration supervisée. Les schémas et modalités de réalisation sont à concevoir.

---

## 11. Parcours utilisateur de référence

### 11.1 Créer et exécuter une investigation

1. L'utilisateur ouvre la page d'OSIA.
2. Il indique un ou plusieurs **indices** et, facultativement, un **objectif**.
3. Il consulte si nécessaire les **paramètres avancés** (sources, profondeur, limites, budget).
4. Il lance la recherche avec des limites admissibles.
5. OSIA affiche son **état réel**, son journal, les découvertes et la consommation disponible.
6. La **synthèse provisoire** et le **graphe** s'enrichissent à mesure que les résultats significatifs sont produits.
7. L'utilisateur peut consulter à tout moment les **fiches**, **preuves** et **relations**, ou intervenir sur les propositions.
8. L'investigation se termine automatiquement si la réponse est suffisamment étayée, ou s'arrête sur limite, erreur ou action humaine.
9. L'interface affiche la cause de l'arrêt, la synthèse stabilisée, les résultats et les pistes pertinentes.
10. L'utilisateur peut consulter un rapport, sauvegarder/exporter manuellement ou lancer explicitement une branche complémentaire.

### 11.2 Vérifier une découverte

1. L'utilisateur sélectionne une conclusion de la synthèse ou un lien du graphe.
2. La fiche contextuelle indique la proposition et son **niveau d'étayage**.
3. Les sources justificatives et dates pertinentes sont consultables.
4. L'utilisateur peut valider, rejeter, corriger ou annoter.
5. L'intervention est historisée, les éléments initiaux sont conservés et les vues dépendantes sont mises à jour ou signalées comme à réanalyser.

### 11.3 Prolonger une recherche

1. OSIA propose une piste **non lancée**.
2. L'utilisateur en examine l'objectif, le point de départ et les limites.
3. Il valide explicitement le lancement de la nouvelle branche.
4. La branche reprend le contexte connu et dispose de son propre suivi.
5. Les vues permettent d'examiner la branche seule ou de la réintégrer à une restitution consolidée.

---

## 12. Modèle conceptuel minimal pour la conception

Cette section exprime des **objets fonctionnels** nécessaires à l'interface ; elle ne fixe ni schéma SQL, ni technologie, ni politique de persistance.

| Concept | Rôle fonctionnel | Liens essentiels |
|---|---|---|
| **Investigation** | Travail principal et objectif initial | Indices, limites, branches, rapports |
| **Branche** | Poursuite explicite ou approfondissement | Parent, contexte hérité, opérations, dépenses, résultats |
| **Opération de recherche** | Action réellement exécutée | Branche, source/connecteur, horodatage, résultat/erreur, consommation |
| **Source / document** | Origine d'une information | Référence, dates, conditions d'accès, éléments collectés |
| **Assertion** | Information ou proposition élémentaire | Source(s), entités/relations, statut d'étayage, historique |
| **Entité** | Personne, organisation, adresse, domaine, document, etc. | Identité, alias, assertions, relations |
| **Relation** | Lien entre deux ou plusieurs entités selon le modèle métier | Type, direction, temporalité, assertions, sources |
| **Décision humaine** | Validation, rejet, correction, annotation et assimilés | Cible, version, action, date, justification facultative |
| **Vue de graphe** | Disposition et filtres d'affichage | Mode, sélection, masquage, groupes, positions |
| **Synthèse / rapport** | Restitution interprétée à un instant donné | Périmètre, conclusions, références, version |

### Invariants de conception

1. **Une même entité métier peut apparaître dans plusieurs branches**, sans que cela impose plusieurs entités distinctes.
2. **Une même source peut étayer plusieurs assertions** ; chaque assertion peut posséder plusieurs sources.
3. **Un lien de navigation entre investigations n'est pas une relation OSINT.**
4. **Le statut d'étayage et le statut de validation humaine sont indépendants.**
5. **Masquer, filtrer ou regrouper un élément ne doit pas le supprimer.**
6. **Une correction n'écrase pas silencieusement la proposition et ses sources initiales.**
7. **Les versions de restitution explicitement conservées sont immuables du point de vue de leur contenu historique.**
8. **Les limitations de consommation restent applicables** aux nouvelles branches, réanalyses et actions provoquées par l'interface.

---

## 13. Critères de recette fonctionnelle du lot C

Les scénarios suivants sont des **tests d'acceptation** découlant des décisions ; ils ne constituent pas une liste de technologies à imposer.

| ID | Scénario | Résultat attendu |
|---|---|---|
| **REC-C-01** | Ouvrir la fiche d'un nœud depuis le graphe. | La fiche apparaît sans changement de page ni perte de sélection. |
| **REC-C-02** | Utiliser l'interface sur un écran étroit. | Saisie, synthèse, graphe et fiches restent consultables et manipulables. |
| **REC-C-03** | Lancer une recherche avec plusieurs indices. | Objectif, indices et paramètres sont pris en compte et accessibles au suivi. |
| **REC-C-04** | Examiner l'avancement d'une recherche exploratoire. | Les opérations et consommations affichées sont réelles ou qualifiées ; aucun faux pourcentage n'est inventé. |
| **REC-C-05** | Atteindre une limite ou arrêter la recherche. | Cause de l'arrêt et résultats partiels sont accessibles ; aucune poursuite implicite. |
| **REC-C-06** | Cliquer une conclusion de synthèse. | Navigation vers les objets/sources qui l'étayent ou identification explicite d'une hypothèse non démontrée. |
| **REC-C-07** | Afficher un lien hypothétique et un lien documenté. | Les conventions graphiques permettent de les distinguer. |
| **REC-C-08** | Appliquer un filtre de graphe puis le supprimer. | Les éléments masqués réapparaissent ; aucune donnée n'a été supprimée. |
| **REC-C-09** | Développer un graphe très fourni. | Exploration progressive et regroupements disponibles ; l'interface reste exploitable. |
| **REC-C-10** | Lire une fiche présentant deux sources différentes pour deux attributs. | La provenance est visible au niveau de chaque attribut concerné. |
| **REC-C-11** | Examiner deux homonymes. | Aucun rapprochement automatique injustifié n'est présenté comme une identité certaine. |
| **REC-C-12** | Valider une hypothèse « à confirmer ». | Statut humain « validé » conservé, sans conversion automatique de l'étayage en « documenté ». |
| **REC-C-13** | Corriger puis annuler une correction. | Historique complet conservé ; vues actualisées sans effacement destructif. |
| **REC-C-14** | Rejeter une relation utilisée dans une conclusion. | La conclusion est réévaluée ou marquée comme nécessitant une réanalyse. |
| **REC-C-15** | Proposer une nouvelle branche après clôture. | La branche n'est pas exécutée avant accord explicite sur son lancement et ses limites. |
| **REC-C-16** | Ouvrir la vue consolidée avec deux branches mentionnant la même entité. | Déduplication justifiée, chemins de découverte conservés, contradictions non masquées. |
| **REC-C-17** | Consulter un rapport. | Rapport lisible dans l'interface sans téléchargement forcé. |
| **REC-C-18** | Actualiser un rapport après approfondissement. | La version antérieure explicitement conservée reste identifiable et non altérée. |
| **REC-C-19** | Solliciter une réanalyse après correction alors qu'un plafond de dépense est atteint. | Aucun appel payant hors budget n'est effectué sans nouvelle autorisation explicite. |

---

## 14. Articulation avec les autres lots et points à traiter ensuite

### Décisions héritées des lots A/B — à respecter

- Recherche OSINT assistée par IA à partir d'un objectif et d'indices.
- Exploration multi-rebonds **bornée** par les règles et budgets autorisés.
- Arrêt automatique dès qu'une réponse est suffisamment étayée.
- Pistes d'approfondissement présentées **sans exécution automatique**.
- Prolongations créées comme branches liées à leur origine, avec limites explicites.
- Provenance vérifiable, distinction entre sources, interprétations de l'IA et décisions humaines.
- Adaptation aux différents modes de consultation autorisés par les sources et connecteurs.

### Domaines désormais encadrés par D, T2 et T7

- **Persistances locales** : ce qui est conservé, à quel endroit, à quel moment et pour combien de temps.
- **Sauvegarde/restauration** : contenu d'une sauvegarde, sélection des investigations, archives et réimport éventuel.
- **Formats d'export** : choix précis des formats destinés à l'humain, au partage et à une réutilisation machine.
- **Paramètres globaux et profils** : valeurs par défaut, réglages persistants, plafonds, sources, éventuels profils de recherche.
- **Données d'accès aux sources** : stockage et protection des clés/API et autres paramètres sensibles.
- **Données de vue et versions** : conservation des positions du graphe, des vues, des rapports et de leurs versions après fermeture de session.
- **Politique de données locales** : effacement, archivage, nettoyage, protection et compatibilité entre versions.

### Modalités à préciser au stade de conception, sans rouvrir les choix C1–C7

- Détails visuels et ergonomiques (dimensions, placements, raccourcis clavier, couleurs et pictogrammes).
- Implémentation des mises à jour temps réel et de la navigation contextuelle.
- Règles exactes et algorithmes de mise en page, regroupement et performance du graphe.
- Modèle opérationnel de déduplication et de rapprochement d'identités, compatible avec validation humaine.
- Conditions de déclenchement d'une régénération de synthèse, et distinction entre mise à jour locale et appel IA.
- Format des journaux et niveau de détail réellement observable par connecteur.
- Règles précises de construction d'une vue consolidée et de gestion des dépendances entre assertions.

**Ces points ne sont pas de nouveaux arbitrages fonctionnels du lot C ; ils précisent comment implémenter les décisions validées.**

---

## 15. Synthèse finale et clôture

Le lot C définit une **interface web unifiée, contextuelle, traçable et orientée investigation**. Son fonctionnement repose sur quatre engagements :

1. **Explorer efficacement :** saisie directe, paramètres avancés accessibles, suivi dynamique, graphe adaptatif et navigation multi-branches.
2. **Comprendre les résultats :** synthèse concise reliée à des fiches et sources identifiables.
3. **Garder le contrôle :** validation et correction humaines, historique réversible, aucune prolongation ni dépense supplémentaire hors des limites consenties.
4. **Restituer sans altérer :** vues par branche ou consolidées, rapports synthétiques ou détaillés, exports manuels, sauvegardes selon T2 et conservation des versions explicitement retenues.

**Décision de clôture :** C1 = C ; C2 = C ; C3 = C ; C4 = C ; C5 = C ; C6 = C ; C7 = C.  
**Statut : lot C validé et clôturé le 05/11/2026.**  
**Étape suivante : conception détaillée et définition précise de la V1 ; le lot D et les lots techniques sont clôturés.**

---

## 16. Historique documentaire

| Version | Date | Modification | Statut |
|---|---|---|---|
| **1.0** | **05/11/2026** | Consolidation des sept arbitrages C1–C7 et de leurs implications fonctionnelles | **Validé** |
