# PROJECT-INIT.md — Procédure de cadrage et d'évolution d'un projet avec une IA

**Version :** 0.3 — 29 octobre 2026  
**Statut :** première version de référence du template — à valider  
**Portée :** indépendante du fournisseur d'IA, du langage, de l'environnement de développement et de l'hébergement.

## 1. Objectif et modes d'utilisation

Transformer une idée ou des échanges de conception en **documentation cohérente et exploitable par plusieurs agents**, puis accompagner les évolutions du projet sans recréer inutilement son cadrage.

La présente procédure couvre trois modes :

| Mode | Déclencheur | Production principale |
| --- | --- | --- |
| **INITIALISATION** | Nouveau projet, souvent après plusieurs conversations de cadrage | Dépôt et référentiels `CADRAGE/`, règles `AGENTS.md`, espace `COWORKAI/`, premières missions |
| **ÉVOLUTION** | Nouvelle fonctionnalité ou extension fonctionnelle d'un projet existant | Spécification autonome dans `roadmap/` et, si nécessaire, mission de réalisation dans `COWORKAI/` |
| **RÉVISION** | Changement d'une décision applicable, d'une règle métier, d'une architecture ou d'une spécification existante | Mise à jour ciblée des références concernées, analyse d'impact et trace de décision |

**L'utilisateur n'a pas à choisir un mode dans une syntaxe particulière.** L'agent l'infère de la demande et explique brièvement son choix si celui-ci modifie la portée du travail. Une évolution qui implique un changement structurant comprend aussi les opérations de RÉVISION nécessaires, idéalement dans la même PR cohérente.

**Principe :** l'utilisateur décide des objectifs, des règles métier et des changements structurants ; les agents proposent les solutions, organisent la documentation et exécutent les opérations ordinaires autorisées.

Le projet peut être conçu librement dans un **espace de travail conversationnel** (par exemple, un Projet ChatGPT), au fil de plusieurs échanges. L'application de cette procédure intervient généralement lors d'une consolidation finale, sans obligation d'écrire un compte rendu Markdown après chaque discussion. L'agent utilise seulement les sources auxquelles il a réellement accès.

## 2. Règles permanentes pour l'agent

1. **Réutiliser le contexte disponible.** Lire les documents existants et retrouver, dans la mesure des accès réels, les échanges de conception pertinents. Ne pas redemander une réponse déjà accessible.
2. **Ne jamais inventer une décision.** Distinguer `VALIDÉ`, `PROPOSÉ`, `OUVERT`, `REPORTÉ`, `REMPLACÉ`. Une suggestion, une hypothèse ou une ancienne discussion n'est pas une validation.
3. **Privilégier les arbitrages groupés.** Poser uniquement les questions qui changent réellement le périmètre ou les choix structurants. Avancer sur les parties non bloquées.
4. **Respecter la source de vérité.** Les décisions durables applicables vivent dans `CADRAGE/` ; les spécifications de fonctionnalités dans `roadmap/` ; les activités et leur traçabilité dans `COWORKAI/`. Ne pas multiplier les copies d'une même règle.
5. **Rester proportionné.** Créer uniquement les fichiers utiles, les lire selon leur pertinence et ne pas transformer une petite évolution en refonte documentaire complète.
6. **Distinguer document, code et preuve.** Une spécification n'est pas du code livré ; un build réussi n'est pas une recette ; une PR ouverte n'est pas un merge ni un déploiement.
7. **Respecter `AGENTS.md`.** La politique permanente d'autonomie, de tests, de sécurité, d'escalade et de livraison s'y trouve. Ne pas inventer une capacité de délégation ou un test non disponible.
8. **Aucune action sensible implicite.** Pas de fusion dans `main`, déploiement de production, mutation irréversible de données réelles, coût, ressource facturable ou publication publique sans autorisation explicite adaptée.
9. **Éviter les surprises.** Préserver la structure et les conventions d'un dépôt existant. Travailler sur une branche de fonctionnalité/documentation et soumettre une PR lorsque l'accès GitHub le permet.

## 3. Phase 0 — Consolider les échanges et sources existants

**Obligatoire lorsqu'une demande s'appuie sur un cadrage antérieur ; facultative pour une idée véritablement nouvelle.**

L'agent :

1. Examine le dépôt, les documents de projet et les conversations **auxquels il a effectivement accès**. Si un outil donne accès aux échanges précédents (par exemple, un Projet ChatGPT), rechercher les décisions pertinentes dans les limites de cet accès.
2. Reconstruit les choix **applicables aujourd'hui**, sans faire un résumé exhaustif de chaque discussion. Relever les propositions remplacées par des décisions plus récentes.
3. Repère, par thème, les statuts `VALIDÉ`, `PROPOSÉ`, `OUVERT`, `REPORTÉ` et `REMPLACÉ`. Une décision `REMPLACÉ` reste une trace historique : **elle ne s'applique plus** et doit, si possible, pointer vers la décision qui la remplace.
4. Confronte ces résultats aux documents et, pour un projet existant, aux conventions du code. Un document ancien n'est pas forcément une instruction actuelle.
5. Signale les conflits **non résolus** et les informations importantes **introuvables** ; n'arbitre pas à la place de l'utilisateur.
6. Présente les arbitrages bloquants sous forme regroupée. Les points mineurs peuvent rester ouverts.

**Limite à expliciter :** l'accès à un espace de travail conversationnel, à un historique partiel ou à une mémoire **ne garantit pas la récupération exhaustive de toutes les conversations**. L'agent ne prétend jamais avoir tout relu s'il ne peut pas l'établir. Pour une décision cruciale non retrouvée ou ambiguë, il demande une confirmation ciblée.

**Livrable interne :** tableau de consolidation par sujet (choix actuel, statut, référence connue, contradiction éventuelle). Ce tableau peut rester temporaire ; il ne devient pas un journal permanent par défaut.

## 4. Organisation documentaire commune

```text
README.md                         Présentation, état du projet et accès à la documentation
AGENTS.md                        Consignes permanentes de collaboration IA
PROJECT-INIT.md                  Cette procédure, utilisée pour initialiser/faire évoluer le projet

CADRAGE/
  README.md                      Index et documents faisant autorité
  FONCTIONNEL.md                 Vision, périmètre, règles métier communes
  TECHNIQUE.md                   Architecture, contraintes et choix techniques applicables
  DESIGN.md                      Design, expérience et ergonomie (si pertinent)
  assets/                        Maquettes et références visuelles utiles (optionnel)

roadmap/
  README.md                      Index des fonctionnalités (à créer si utile)
  01-fonctionnalite.md           Spécification autonome, datée et avec statut
  ...                            Autres évolutions, uniquement au besoin

COWORKAI/
  README.md                      Tableau de bord léger : missions, liens et blocages
  DECISIONS.md                   Journal daté des arbitrages significatifs du travail
  missions/                      Tâches actives, lots, responsables si connus
  rapports/                      Revues, tests, audits, passations et résultats

.github/
  PULL_REQUEST_TEMPLATE.md       Modèle de PR : portée, tests, limites et références
  workflows/                     CI adaptée à la technologie, seulement quand pertinente

scripts/                          Scripts communs ou spécifiques, au besoin
```

Les dossiers facultatifs n'ont pas à être créés artificiellement ; Git ne versionne pas les répertoires vides (utiliser `.gitkeep` uniquement si la présence du dossier est utile). Le préfixe numérique d'un fichier `roadmap/` indique seulement **l'ordre de création ou de classement**, **pas sa priorité** ; les priorités se définissent dans les documents et missions.

Pour un projet sans interface graphique, `DESIGN.md` peut décrire l'expérience CLI/API ou être marqué non applicable. Les conventions de noms ci-dessus servent aux **nouveaux** projets : ne pas renommer automatiquement les fichiers bien établis d'un dépôt existant.

### Responsabilité de chaque emplacement

| Emplacement | Question traitée | Durée de vie |
| --- | --- | --- |
| `AGENTS.md` | **Comment** les agents travaillent-ils, valident-ils et escaladent-ils ? | Stable, modifiable délibérément |
| `CADRAGE/` | **Quelles décisions produit/architecture/design s'appliquent ?** | Référence stable, révisée après décision |
| `roadmap/` | **Quelle fonctionnalité veut-on ajouter et comment vérifier son acceptation ?** | Spécifications par fonctionnalité, avec statut ; pas de journal d’exécution |
| `COWORKAI/` | **Que font les agents, qu'ont-ils constaté et que reste-t-il ?** | Vivant, mis à jour au fil des missions |
| Git + CI | **Quelles modifications et vérifications ont réellement eu lieu ?** | Preuves techniques ; éviter le journal de chaque commit |

Les agents doivent pouvoir distinguer **spécification de fonctionnalité** (`roadmap/`) et **mission d'implémentation/revue** (`COWORKAI/missions/`). Une spécification peut générer plusieurs missions ; une mission peut citer plusieurs spécifications.

Une décision d'architecture ou de métier durable prise pendant une mission doit être **reflétée dans `CADRAGE/`**, avec un renvoi à son contexte dans `COWORKAI/DECISIONS.md` si significatif. Le journal n'est pas une deuxième source de vérité.

### Ressources visuelles

Les maquettes et illustrations servant de référence peuvent être placées dans `CADRAGE/assets/`, avec des liens depuis `CADRAGE/DESIGN.md`. Utiliser des noms explicites et, si utile, des versions. Les fichiers lourds ou gérés dans un outil externe peuvent être simplement référencés avec leur emplacement ; ne pas dupliquer sans nécessité. Les assets finaux de l'application restent dans les chemins prévus par son architecture.

### Lien avec `AGENTS.md`

Le `AGENTS.md` **du futur template** doit citer `PROJECT-INIT.md` et préciser : « À consulter lors de l'initialisation d'un projet, d'une évolution fonctionnelle à cadrer ou d'une révision documentaire demandée ; ne pas relire la procédure à chaque petite intervention de code. »

La **politique d'escalade** reste dans `AGENTS.md` ; les problèmes escaladés, décisions et réponses concrètes se suivent dans `COWORKAI/`. Ne pas dupliquer une deuxième politique permanente d'escalade.

## 5. Mode INITIALISATION — nouveau projet

La conception peut s'étaler sur plusieurs conversations libres. Les phases A–D servent à **consolider ou compléter** le travail déjà effectué, non à imposer un questionnaire répétitif.

### Phase A — Vision et contraintes

Synthétiser le problème à résoudre, les utilisateurs visés, les résultats attendus, les supports, les contraintes de budget, confidentialité, hébergement, maintenance et le niveau d'avancement.

Regrouper les seuls arbitrages structurants manquants. **Livrable :** vision brève et frontières du projet.

### Phase B — Cadrage fonctionnel

Préparer `CADRAGE/FONCTIONNEL.md` :

- Objectifs et terminologie, règles métier et utilisateurs.
- Parcours principaux et cas d'erreur, rôles et permissions si nécessaires.
- Objets et états métier importants.
- Périmètre **V1/MVP**, hors périmètre et évolutions envisagées.
- Critères d'acceptation concrets pour les fonctions structurantes.

Créer des cadrages supplémentaires (`PARCOURS.md`, `DONNEES-METIER.md`, etc.) uniquement quand la complexité le justifie ; les répertorier dans `CADRAGE/README.md`.

L'utilisateur valide les choix métier structurants ; une hypothèse reste `PROPOSÉE` tant qu'elle ne l'a pas été.

### Phase C — Cadrage technique

Préparer `CADRAGE/TECHNIQUE.md` :

- Choix d'architecture et technologies retenues, avec motivations synthétiques.
- Composants, intégrations et circulation des données.
- Authentification, autorisations, secrets, sécurité et confidentialité.
- Stockage, sauvegarde, reprise et observabilité selon les risques.
- Environnements, déploiement, coûts éventuels et contraintes de maintenance.
- Stratégie de tests, outils disponibles et limites.

Séparer `VALIDÉ`, `PROPOSÉ` et `OUVERT`. L'agent tranche les détails ordinaires réversibles ; il remonte les compromis majeurs et coûts. Ne pas créer de ressources payantes ou de production au seul motif qu'elles sont mentionnées dans le cadrage.

### Phase D — Design et expérience

Préparer `CADRAGE/DESIGN.md` si pertinent :

- Direction visuelle, références, terminologie et ton.
- Navigation, parcours d'interface, composants et états (vide, chargement, erreur, succès).
- Responsive, accessibilité et contraintes de marque.
- Choix `VALIDÉS` et options `PROPOSÉES`.

Les maquettes utiles sont enregistrées ou référencées depuis `CADRAGE/assets/` ; ne pas considérer un aperçu exploratoire comme une charte validée.

### Phase E — Préparer le dépôt

**Après un cadrage suffisant, avant d'écrire les fichiers définitifs dans GitHub.**

1. Si un dépôt existe déjà, examiner son contenu et ses conventions ; **le réutiliser**.
2. Sinon, proposer la création depuis le template commun. **La création et la visibilité (privé/public) nécessitent un choix explicite de l'utilisateur.** Ne pas supposer qu'un projet doit être public.
3. Une fois l'accès autorisé, créer une **branche d'initialisation** depuis la branche principale.
4. Si l'agent ne peut pas créer ou modifier le dépôt, produire les fichiers localement ou sous forme de livrables, en indiquant clairement ce qui reste à publier.

Ne pas imposer un dépôt au début des conversations de découverte. Le dépôt documentaire peut aussi être créé plus tôt, à la demande de l'utilisateur.

### Phase F — Remplir les référentiels et préparer les travaux

- Compléter `README.md`, `AGENTS.md` et les documents `CADRAGE/` à partir des décisions applicables.
- Adapter les fichiers modèle, sans recopier leurs exemples comme de vraies décisions.
- Préparer `COWORKAI/README.md`, le journal daté, et une première mission **limitée au travail utile**.
- Créer éventuellement une première spécification `roadmap/` lorsque le V1 comporte un chantier méritant son propre document.
- Définir les dépendances, compétences nécessaires, critères d'acceptation et vérifications du premier lot.
- Ne pas générer un backlog détaillé de dizaines de tâches hypothétiques.

### Phase G — Vérifier et ouvrir la PR

1. Vérifier les liens Markdown, références, statuts, champs provisoires et contradictions actives entre les cadrages.
2. Vérifier que `AGENTS.md` référence les documents réels et `PROJECT-INIT.md`.
3. Vérifier l'absence de secrets, identifiants sensibles et modifications non prévues.
4. Soumettre la documentation sur la branche dédiée et ouvrir une **Pull Request** exposant décisions, questions ouvertes, fichiers, vérifications réellement effectuées et limites.
5. **Laisser la fusion à l'utilisateur.** Aucun déploiement n'est implicitement autorisé.

## 6. Mode ÉVOLUTION — nouvelle fonctionnalité

Une spécification de fonctionnalité doit être **autonome** : besoins, décisions, parcours, intégration, sécurité, lots si nécessaires et critères d'acceptation. Elle n'est pas une preuve de développement ou de déploiement. La structure minimale peut être directement copiée depuis la procédure, **sans fichier d'exemple propre à un autre projet** :

```markdown
# <Fonctionnalité> — Spécification
**Statut :** <VALIDÉ / PROPOSÉ / OUVERT / REPORTÉ>  
**Date :** <AAAA-MM-JJ>

## 1. Contexte et objectif
## 2. Périmètre et hors périmètre
## 3. Décisions validées et points ouverts
## 4. Parcours et cas d’erreur
## 5. Intégration technique, données et sécurité
## 6. Lots de réalisation (si nécessaires)
## 7. Critères de recette / d’acceptation
## 8. Références et dépendances
```

**Remplir uniquement les sections utiles**, avec des éléments vérifiables et des statuts explicites ; ne jamais laisser ces en-têtes vides en prétendant qu'une spécification est complète.

**Cas d'un dépôt sans cadrage :** si le dépôt ne comporte pas de `CADRAGE/` ou de référentiel équivalent, le signaler et proposer une **INITIALISATION partielle** limitée aux décisions structurantes nécessaires. Ne pas inventer des règles absentes ; poursuivre les parties de l'évolution qui ne dépendent pas de ces arbitrages.

1. **Consolider** la ou les conversations portant sur la nouvelle fonctionnalité (phase 0), en respectant les décisions validées et les incertitudes.
2. **Lire les références utiles** du dépôt existant : `AGENTS.md`, cadrages concernés, architecture et code si l'intégration le nécessite. Ne pas relire tout le dépôt sans justification.
3. **Vérifier la cohérence** avec le produit, les rôles, la sécurité, le design, les dépendances et les travaux en cours.
4. **Créer une spécification autonome** dans `roadmap/` : contexte, objectif, statut (`VALIDÉ`, `PROPOSÉ`, points `OUVERTS`), périmètre / hors périmètre, parcours, solutions envisagées si utile, exigences techniques, sécurité, découpage en lots, critères de recette et liens vers les références.
5. **Mettre à jour seulement ce qui est nécessaire** dans `CADRAGE/` si la nouvelle fonctionnalité implique une décision générale applicable. Si elle contredit une décision existante, traiter aussi le **mode RÉVISION** : ne pas créer une seconde vérité incompatible.
6. Si des travaux sont prêts, ouvrir une ou plusieurs **missions de réalisation** dans `COWORKAI/` qui référencent la spécification. Une roadmap n'est pas un journal d'exécution.
7. Publier par **branche et PR**, en conservant le merge sous contrôle utilisateur.

**Par défaut :** une fonctionnalité autonome et compatible ne doit pas déclencher la réécriture des trois cadrages généraux ni la création d'une nouvelle procédure. Conserver la spécification comme source de détail de la fonctionnalité.

## 7. Mode RÉVISION — changer une décision applicable

Ce mode concerne une décision métier, technique, graphique ou une spécification **déjà applicable**, pas un simple ajout indépendant.

1. Identifier la **décision actuelle**, le document qui fait autorité et le motif du changement.
2. Vérifier que le changement structurant est **explicitement validé** par l'utilisateur. À défaut, proposer les options, leurs conséquences et laisser le point `OUVERT`.
3. Repérer les documents, spécifications `roadmap/`, missions en cours, tests et composants potentiellement affectés. Proportionner la recherche au changement.
4. Modifier **la référence applicable** et les documents devenus contradictoires ; préserver la distinction entre décision validée et simple proposition.
5. Tracer dans `COWORKAI/DECISIONS.md` **si le changement est significatif** : date, ancienne décision, nouvelle décision, justification, statut, référence documentaire et, lorsque disponible, PR/commit.
6. Ajuster ou signaler les missions touchées, sans déclarer le code corrigé tant que les modifications ne sont pas réalisées et vérifiées.
7. Préparer une **PR ciblée** avec résumé de l'impact, contrôles effectués et éventuels arbitrages encore ouverts.

**Règle de cohérence :** le journal explique *quand et pourquoi* une décision a évolué ; `CADRAGE/` et les spécifications applicables indiquent *ce qui vaut maintenant*.

## 8. Statuts de mission, responsabilités et retours en arrière

La progression type d'une mission est :

`À FAIRE → EN COURS → CODE LIVRÉ → TESTS VALIDÉS → REVUE VALIDÉE → PR PRÊTE → FUSIONNÉ → DÉPLOYÉ`

Cette chaîne est une **grille d'information**, pas l'obligation que chaque mission passe par toutes les étapes : une mission purement documentaire, par exemple, n'a pas de « code livré ».

| Action | Autorité et preuve |
| --- | --- |
| Passer à `EN COURS`, signaler `CODE LIVRÉ` | Agent chargé de la mission, avec références aux commits et limites |
| Déclarer `TESTS VALIDÉS` | Agent après exécution des contrôles réellement pertinents, avec résultats et environnement ; ne pas confondre avec recette utilisateur |
| Déclarer `REVUE VALIDÉE` | Agent ou relecteur désigné, **après revue effectivement réalisée** ; pas d'auto-affirmation non vérifiée |
| Déclarer `PR PRÊTE` | Agent lorsque la PR existe et que ses critères de préparation sont satisfaits |
| Repasser de `TESTS VALIDÉS` ou `REVUE VALIDÉE` à `EN COURS` | Agent/relecteur autorisé **si une régression, un contrôle manquant ou une nouvelle preuve l'exige** ; journaliser brièvement le motif |
| Déclarer `FUSIONNÉ` | Uniquement après constat du merge réel ; **décision de merger réservée à l'utilisateur** |
| Déclarer `DÉPLOYÉ` | Uniquement après constat du déploiement réel ; déploiement de production soumis à autorisation explicite |

Une réouverture n'efface ni les anciennes preuves ni l'historique Git. Les échecs de CI et les revues défavorables peuvent bloquer l'avancement. Les besoins de recette manuelle doivent rester visibles séparément de la réussite des tests automatisés.

La politique générale d'autonomie et d'escalade se trouve dans `AGENTS.md`. Un blocage technique peut être confié à un agent plus adapté **si ce moyen est réellement disponible** ; sinon, le signaler sans promettre une délégation fictive.

## 9. Escalade pendant les trois modes

La politique permanente d'escalade est dans **`AGENTS.md`**, qui fait autorité ; ne pas la dupliquer ici. Cette section ne précise que son application propre aux modes :

- **INITIALISATION (phase 0 et phase A)** : regrouper les arbitrages structurants manquants en une seule passe ; ne pas ouvrir de PR qui exigerait des choix métier non arbitrés.
- **ÉVOLUTION** : une contradiction avec une décision applicable de `CADRAGE/` déclenche le mode RÉVISION ou une demande d'arbitrage explicite ; ne jamais écrire une seconde vérité incompatible.
- **RÉVISION** : aucun changement structurant applicable sans validation explicite de l'utilisateur ; à défaut, présenter les options et leurs conséquences en laissant le point `OUVERT`.

Les escalades réelles et leur résolution se suivent dans `COWORKAI/` si elles sont significatives, sans créer un journal de chaque commande ou échange.

## 10. Critères de sortie et compte rendu

### INITIALISATION — « prêt à développer »

- [ ] Vision et limites du premier périmètre compréhensibles et validées.
- [ ] Règles métier importantes arbitrées ou signalées comme bloquantes.
- [ ] Choix techniques structurants validés ; autres inconnues visibles.
- [ ] Design/ergonomie suffisamment définis pour le premier lot, selon le type de projet.
- [ ] `AGENTS.md` référence les documents pertinents et `PROJECT-INIT.md`.
- [ ] Index `CADRAGE/README.md` cohérent et sans contradiction active connue.
- [ ] Premier lot décrit avec critères de fin et tests envisagés.
- [ ] Branche et PR d'initialisation disponibles si le dépôt est accessible.

### ÉVOLUTION — « spécification exploitable »

- [ ] Décisions validées et points ouverts clairement séparés.
- [ ] Spécification autonome liée aux bons cadrages.
- [ ] Pas de conflit non résolu avec les décisions applicables.
- [ ] Lots, critères de recette et dépendances suffisamment clairs pour confier le développement.
- [ ] PR documentaire prête si publication GitHub demandée et possible.

### RÉVISION — « documentation de nouveau cohérente »

- [ ] Nouvelle décision structurante confirmée.
- [ ] Références applicables mises à jour sans laisser des règles incompatibles.
- [ ] Impacts sur roadmap, missions et code identifiés ou signalés.
- [ ] Journal de décision mis à jour si le changement est significatif.
- [ ] PR documente les changements et leurs limites.

Pour tout mode, le compte rendu final indique **ce qui a effectivement été créé ou modifié**, les décisions validées, les questions restantes, les contrôles réellement effectués, la branche/PR si elles existent, et les actions encore nécessaires. Ne jamais déclarer de test, de commit, de PR, de merge ou de déploiement fictif.

## 11. Maintenance et compatibilité du template

Le template fournit des **modèles et conventions**, non des décisions métier imposées à chaque projet. Une mise à jour du template ne doit jamais écraser automatiquement `CADRAGE/` ou les fichiers vivants d'un projet. Une reprise versionnée (par exemple avec Copier) doit être présentée comme un changement contrôlable, de préférence par PR.

Les mécanismes spécifiques aux plateformes (GitHub Template Repository, CI, connecteurs et autorisations) ne doivent pas empêcher l'utilisation locale de la procédure. Elle peut devenir ultérieurement un skill pour un agent compatible ; **aucun moteur de skills n'est requis pour cette version**.