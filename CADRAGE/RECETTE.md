# OSIA — Référentiel de recette et traçabilité des contrôles

**Édition 1.1 — 06/11/2026.** Ce document décrit des critères à vérifier pendant le développement. **Aucun test applicatif n’a été exécuté au titre de cette consolidation.**

## 1. Corpus de contrôle

69 critères fonctionnels d’origine sont conservés dans les lots A–D. S’y ajoutent 75 scénarios techniques dérivés (un par décision T2–T8 ou thème EXEC) et 12 scénarios de cohérence transversale : **156 scénarios de référence**. Ce nombre mesure la couverture documentaire ; il ne constitue ni un taux de conformité ni une couverture de code.

Pour chaque réalisation, consigner identifiant, données de test, environnement, procédure, résultat attendu/obtenu et preuve d’exécution. Les scénarios techniques sont des dérivations vérifiables des exigences, pas de nouveaux arbitrages produit. Les contrôles de sécurité, concurrence, corruption et interruption doivent inclure les chemins d’échec.

## 2. Critères fonctionnels conservés

Les formulations complètes figurent dans les lots liés ; les identifiants sont conservés. Le libellé REC-D3-02 est précisé pour distinguer engagement OSIA et facturation externe (audit COH-17).

| ID | Lot et scénario |
| --- | --- |
| S01 | [A](LOTS/A.md) — Objectif explicite et sous-questions |
| S02 | [A](LOTS/A.md) — Objectif biaisé |
| S03 | [A](LOTS/A.md) — Décompte des rebonds |
| S04 | [A](LOTS/A.md) — Sources désactivées |
| S05 | [A](LOTS/A.md) — Homonymes |
| S06 | [A](LOTS/A.md) — Rejet et propagation |
| S07 | [A](LOTS/A.md) — Rejet local de pertinence |
| S08 | [A](LOTS/A.md) — Réponse trouvée avant la limite |
| S09 | [A](LOTS/A.md) — Prolongation au-delà de la profondeur initiale |
| S10 | [A](LOTS/A.md) — Budget atteint |
| S11 | [A](LOTS/A.md) — Sources contradictoires dans le temps |
| S12 | [A](LOTS/A.md) — Découverte d'une branche et synthèse mère |
| S13 | [A](LOTS/A.md) — Investigation interrompue |
| S14 | [A](LOTS/A.md) — Pistes secondaires |
| S15 | [A](LOTS/A.md) — Investigation à plusieurs sous-objectifs |
| B-ACC-01 | [B](LOTS/B.md) — Un connecteur peut être désactivé sans bloquer les autres. |
| B-ACC-02 | [B](LOTS/B.md) — Un connecteur ajouté via le contrat commun est exploitable sans modifier la logique métier centrale. |
| B-ACC-03 | [B](LOTS/B.md) — Une recherche peut mobiliser plusieurs familles de sources et plusieurs modes autorisés. |
| B-ACC-04 | [B](LOTS/B.md) — Un navigateur avancé n'est invoqué que si son usage est justifié, permis et budgété. |
| B-ACC-05 | [B](LOTS/B.md) — L'IA ne peut lancer directement un appel refusé par le contrôleur indépendant. |
| B-ACC-06 | [B](LOTS/B.md) — Une requête équivalente déjà satisfaite peut réutiliser un résultat valide plutôt que générer un nouvel appel. |
| B-ACC-07 | [B](LOTS/B.md) — Une simple adresse commune n'est jamais étiquetée automatiquement « affiliation démontrée ». |
| B-ACC-08 | [B](LOTS/B.md) — Une conclusion affichée peut être reliée aux éléments sources et à leur période de validité. |
| B-ACC-09 | [B](LOTS/B.md) — Deux versions historiques compatibles d'une information ne sont pas nécessairement considérées contradictoires. |
| B-ACC-10 | [B](LOTS/B.md) — Deux opérations simultanées ne peuvent réserver la même portion de budget disponible. |
| B-ACC-11 | [B](LOTS/B.md) — Une opération payante dont le risque de dépassement n'est pas maîtrisé n'est pas exécutée automatiquement. |
| B-ACC-12 | [B](LOTS/B.md) — Une API défaillante est isolée et peut être remplacée par une alternative autorisée. |
| B-ACC-13 | [B](LOTS/B.md) — Une correction sensible de connecteur ne peut être activée en production sans validation explicite. |
| B-ACC-14 | [B](LOTS/B.md) — Les vérifications périodiques sont soumises à des plafonds de ressources. |
| B-ACC-15 | [B](LOTS/B.md) — Lorsque l'objectif est suffisamment étayé, OSIA s'arrête et laisse les autres pistes à l'état de propositions. |
| B-ACC-16 | [B](LOTS/B.md) — Une prolongation autorisée reprend le contexte sous une nouvelle branche, avec nouveaux plafonds explicites. |
| REC-C-01 | [C](LOTS/C.md) — Ouvrir la fiche d'un nœud depuis le graphe. |
| REC-C-02 | [C](LOTS/C.md) — Utiliser l'interface sur un écran étroit. |
| REC-C-03 | [C](LOTS/C.md) — Lancer une recherche avec plusieurs indices. |
| REC-C-04 | [C](LOTS/C.md) — Examiner l'avancement d'une recherche exploratoire. |
| REC-C-05 | [C](LOTS/C.md) — Atteindre une limite ou arrêter la recherche. |
| REC-C-06 | [C](LOTS/C.md) — Cliquer une conclusion de synthèse. |
| REC-C-07 | [C](LOTS/C.md) — Afficher un lien hypothétique et un lien documenté. |
| REC-C-08 | [C](LOTS/C.md) — Appliquer un filtre de graphe puis le supprimer. |
| REC-C-09 | [C](LOTS/C.md) — Développer un graphe très fourni. |
| REC-C-10 | [C](LOTS/C.md) — Lire une fiche présentant deux sources différentes pour deux attributs. |
| REC-C-11 | [C](LOTS/C.md) — Examiner deux homonymes. |
| REC-C-12 | [C](LOTS/C.md) — Valider une hypothèse « à confirmer ». |
| REC-C-13 | [C](LOTS/C.md) — Corriger puis annuler une correction. |
| REC-C-14 | [C](LOTS/C.md) — Rejeter une relation utilisée dans une conclusion. |
| REC-C-15 | [C](LOTS/C.md) — Proposer une nouvelle branche après clôture. |
| REC-C-16 | [C](LOTS/C.md) — Ouvrir la vue consolidée avec deux branches mentionnant la même entité. |
| REC-C-17 | [C](LOTS/C.md) — Consulter un rapport. |
| REC-C-18 | [C](LOTS/C.md) — Actualiser un rapport après approfondissement. |
| REC-C-19 | [C](LOTS/C.md) — Solliciter une réanalyse après correction alors qu'un plafond de dépense est atteint. |
| REC-D1-01 | [D](LOTS/D.md) — fermer et rouvrir OSIA retrouve une investigation, ses branches, ses sources et ses décisions enregistrées. |
| REC-D1-02 | [D](LOTS/D.md) — une interruption durant l'écriture ne produit pas de restauration silencieusement incohérente. |
| REC-D2-01 | [D](LOTS/D.md) — configurer deux fournisseurs et affecter des modèles à des tâches distinctes. |
| REC-D2-02 | [D](LOTS/D.md) — une clé API absente de la mémoire persistante par défaut ne figure ni dans les exports ni dans les journaux. |
| REC-D2-03 | [D](LOTS/D.md) — une alternative de modèle non autorisée ne peut être utilisée automatiquement. |
| REC-D3-01 | [D](LOTS/D.md) — un profil personnalisé et des limites d'investigation sont enregistrés et appliqués. |
| REC-D3-02 | [D](LOTS/D.md) — aucune nouvelle dépense OSIA ne peut être engagée au-delà de l'autorisation même lors d'appels parallèles ou de relances ; les écarts de facture fournisseur restent distingués et visibles (T8.4). |
| REC-D4-01 | [D](LOTS/D.md) — purger le cache temporaire ne détruit pas une preuve nécessaire à une conclusion conservée. |
| REC-D4-02 | [D](LOTS/D.md) — une actualisation préserve la provenance et l'ancienne version probante. |
| REC-D5-01 | [D](LOTS/D.md) — exporter puis réimporter un `.osia` restitue branches, graphe, sources et historique sans nouveaux appels IA. |
| REC-D5-02 | [D](LOTS/D.md) — un conflit d'import est détecté et ne provoque aucun écrasement silencieux. |
| REC-D5-03 | [D](LOTS/D.md) — un `.html` exporté s'ouvre hors ligne, permet la navigation interactive et ne déclenche aucun appel externe automatique. |
| REC-D5-04 | [D](LOTS/D.md) — les données désélectionnées d'un HTML sont réellement absentes du fichier produit. |
| REC-D5-05 | [D](LOTS/D.md) — une archive chiffrée requiert le déverrouillage ; une archive corrompue est refusée avec diagnostic. |
| REC-D6-01 | [D](LOTS/D.md) — les transmissions externes respectent les connecteurs/fournisseurs autorisés. |
| REC-D6-02 | [D](LOTS/D.md) — les modes archive, suppression et effacement global ont des portées distinctes, explicites et confirmées. |
| REC-D7-01 | [D](LOTS/D.md) — modifier un profil global n'augmente pas le budget d'une investigation déjà lancée. |
| REC-D7-02 | [D](LOTS/D.md) — une nouvelle restriction globale empêche les opérations futures incompatibles sans réécrire l'historique. |
| REC-D7-03 | [D](LOTS/D.md) — une erreur réseau, API ou stockage conserve les résultats déjà enregistrés et offre une résolution supervisée. |

## 3. Scénarios techniques dérivés

| ID | Décision | Déclencheur | Résultat attendu |
| --- | --- | --- | --- |
| AC-EXEC-01 | [EXEC-01](LOTS/T1.md) | Exécuter le même cas par CLI/API sans frontend installé | Les règles métier, données et limites proviennent du même moteur ; aucune dépendance à une interface graphique. |
| AC-EXEC-02 | [EXEC-02](LOTS/T1.md) | Installer selon les modes poste et serveur | Les paramètres et modules effectifs correspondent au mode ; leur cycle de vie est documenté et aucun changement de mode ne perd les données. |
| AC-EXEC-03 | [EXEC-03](LOTS/T1.md) | Installer avec et sans frontend web | Le backend reste utilisable ; en usage serveur, l’API reste disponible avec ses protections ; aucune dépendance obligatoire à Docker. |
| AC-EXEC-04 | [EXEC-04](LOTS/T1.md) | Déconnecter puis reconnecter un client de suivi | REST restitue l’état persistant et SSE reprend le suivi selon le contrat ; aucune recherche n’est créée en double. |
| AC-EXEC-05 | [EXEC-05](LOTS/T1.md) | Tenter un accès serveur non authentifié, avec et sans frontend | Accès refusé ; l’accès distant permis utilise HTTPS ; l’installation locale ne s’expose pas implicitement. |
| AC-EXEC-06 | [EXEC-06](LOTS/T1.md) | Détecter une version applicative plus récente | Notification disponible ; aucune mise à jour applicative imposée automatiquement ; migration supervisée. |
| AC-EXEC-07 | [EXEC-07](LOTS/T1.md) | Examiner le périmètre V1 et les dépendances du moteur | Le client GNOME est différé ; aucune obligation d’introduire Rust dans le moteur Python initial. |
| AC-T2-01 | [T2.1](LOTS/T2.md) | Persister et relire une investigation | PostgreSQL est la base principale ; le navigateur ne porte pas la référence métier. |
| AC-T2-02 | [T2.2](LOTS/T2.md) | Collecter deux fichiers identiques depuis deux sources | Déduplication physique possible par SHA-256 ; les deux provenances et dates restent distinctes. |
| AC-T2-03 | [T2.3](LOTS/T2.md) | Configurer des répertoires adaptés aux deux modes | Configuration, données, cache, journaux et sauvegardes sont séparés et protégés par les permissions adaptées. |
| AC-T2-04 | [T2.4](LOTS/T2.md) | Interrompre l’écriture entre fichier et base puis reprendre | Le protocole récupère ou signale l’état incomplet ; aucune référence silencieusement incohérente n’est acceptée. |
| AC-T2-05 | [T2.5](LOTS/T2.md) | Effectuer une sauvegarde manuelle puis configurer une programmation | La programmation reste facultative ; destination, rétention et erreurs sont visibles/configurables. |
| AC-T2-06 | [T2.6](LOTS/T2.md) | Sauvegarder pendant des écritures, puis restaurer sur une instance de test | La base et les preuves représentent un état cohérent vérifié par manifeste, sans arrêt complet requis du moteur. |
| AC-T2-07 | [T2.7](LOTS/T2.md) | Activer une protection au repos puis examiner temporaires et sauvegardes concernées | Le périmètre sensible choisi est couvert ; les clés et limites de récupération sont documentées. |
| AC-T2-08 | [T2.8](LOTS/T2.md) | Atteindre un seuil disque pendant une collecte | Alerte et suspension propre si nécessaire ; nettoyage limité aux éléments purgeables, sans suppression automatique des preuves conservées. |
| AC-T3-01 | [T3.1](LOTS/T3.md) | Inspecter la pile du moteur initial | Python principal ; aucun moteur Rust additionnel obligatoire sans besoin démontré. |
| AC-T3-02 | [T3.2](LOTS/T3.md) | Modifier un adaptateur sans changer les responsabilités métier | Le monolithe conserve des contrats de modules explicites ; aucun microservice obligatoire ajouté par anticipation. |
| AC-T3-03 | [T3.3](LOTS/T3.md) | Lancer le cœur sans UI | CLI, API/service et appels internes prévus fonctionnent selon leurs contrats, sans dupliquer le métier. |
| AC-T3-04 | [T3.4](LOTS/T3.md) | Recevoir une proposition IA hors autorisation | Le moteur de politiques la refuse ; l’orchestrateur ne modifie pas ses propres limites. |
| AC-T3-05 | [T3.5](LOTS/T3.md) | Exécuter plusieurs E/S et un traitement lourd | Concurrence asynchrone et processus adaptés respectent les limites de l’hôte, de source et de budget. |
| AC-T3-06 | [T3.6](LOTS/T3.md) | Redémarrer après un appel externe au résultat inconnu | État et journal permettent réconciliation ; aucun rejeu facturable aveugle. |
| AC-T3-07 | [T3.7](LOTS/T3.md) | Présenter un message externe de version ou structure invalide | Contrat vérifié ; refus/diagnostic explicite ; migrations/compatibilités documentées. |
| AC-T3-08 | [T3.8](LOTS/T3.md) | Activer une extension déclarant de nouvelles permissions | Manifeste vérifié et autorisation adaptée ; le niveau d’isolation ne repose pas sur un simple sous-processus. |
| AC-T3-09 | [T3.9](LOTS/T3.md) | Déclencher un appel modèle depuis chaque composant | Tous passent par le courtier et ses politiques ; aucun contournement par connecteur. |
| AC-T3-10 | [T3.10](LOTS/T3.md) | Suivre une assertion depuis la sortie jusqu’à la collecte | Original/extrait conservable, normalisation, extraction, interprétation et preuve restent attribuables. |
| AC-T3-11 | [T3.11](LOTS/T3.md) | Faire concourir deux opérations pour la même enveloppe | Réservations atomiques ; aucun engagement au-delà de la limite ; coût non borné refusé ou soumis à autorisation adaptée. |
| AC-T3-12 | [T3.12](LOTS/T3.md) | Simuler indisponibilité, quota, erreur permanente et interruption | Traitements et reprises adaptés, limités ; résultats partiels conservés ; pas de double coût aveugle. |
| AC-T3-13 | [T3.13](LOTS/T3.md) | Lire les journaux d’une opération et d’une erreur | Identifiants de corrélation, temps, états, durées et coûts utiles présents ; secrets absents ; métriques avancées non présumées livrées. |
| AC-T3-14 | [T3.14](LOTS/T3.md) | Exécuter la recette avec substituts de sources et d’IA | Cas unitaires, intégration, contrats, bout en bout et non-régression reproductibles sans facture API. |
| AC-T4-01 | [T4.1](LOTS/T4.md) | Faire apparaître une découverte qui change le plan | Révision et sous-objectifs historisés ; actions nouvelles contrôlées par les politiques. |
| AC-T4-02 | [T4.2](LOTS/T4.md) | Redémarrer l’ordonnanceur avec des tâches dépendantes | File et états PostgreSQL durables ; reprise coordonnée, sans Redis/RabbitMQ/Celery obligatoires. |
| AC-T4-03 | [T4.3](LOTS/T4.md) | Autoriser une prolongation après arrêt | Branche liée, contexte réutilisé, limites explicites ; la nouvelle profondeur ne remet pas les dépenses à zéro. |
| AC-T4-04 | [T4.4](LOTS/T4.md) | Saturer un quota de concurrence simulé | Le parallélisme s’adapte aux limites de source/hôte/budget sans les contourner. |
| AC-T4-05 | [T4.5](LOTS/T4.md) | Proposer deux pistes dont une redondante | Priorisation explicable selon utilité/coût/fiabilité ; pas de nouvelle recherche inutile ni d’autorisation fondée sur le seul score IA. |
| AC-T4-06 | [T4.6](LOTS/T4.md) | Obtenir une réponse étayée avant profondeur maximale | Exploration arrêtée ; pistes restantes affichées sans exécution ; qualité et motif d’arrêt distincts. |
| AC-T4-07 | [T4.7](LOTS/T4.md) | Annuler ou interrompre une tâche externe en cours | État et réservation réconciliés ; aucune hypothèse injustifiée de gratuité ou de non-exécution. |
| AC-T4-08 | [T4.8](LOTS/T4.md) | Injecter une boucle de pistes et une demande IA de lever les limites | Cycles/répétitions et plafonds indépendants empêchent l’emballement ; l’IA ne peut désactiver les garde-fous. |
| AC-T4-09 | [T4.9](LOTS/T4.md) | Observer tâches, découvertes, coûts, erreurs et arrêt | Événements et état accessibles via moteur/API/SSE, y compris sans frontend web. |
| AC-T5-01 | [T5.1](LOTS/T5.md) | Activer un connecteur expérimental | Capacités, coûts et permissions déclarés ; autorisation explicite et isolation adaptée. |
| AC-T5-02 | [T5.2](LOTS/T5.md) | Tenter un accès fichier/réseau hors périmètre depuis un traitement restreint | Restrictions Linux effectives ; limites CPU/mémoire appliquées ; sous-processus seul non présenté comme sandbox. |
| AC-T5-03 | [T5.3](LOTS/T5.md) | Rencontrer une page dynamique puis un CAPTCHA | Playwright isolé seulement si justifié/autorisé ; aucun contournement ; téléchargements et provenance contrôlés. |
| AC-T5-04 | [T5.4](LOTS/T5.md) | Suivre une redirection vers une ressource interne non autorisée | Politique réseau centrale bloque ; domaines, volumes, délais et quotas restent contrôlés. |
| AC-T5-05 | [T5.5](LOTS/T5.md) | Utiliser puis révoquer une clé, examiner sorties et traces | Cloisonnement et révocation effectifs ; aucune persistance par défaut, aucun secret dans logs, exports ou prompts. |
| AC-T5-06 | [T5.6](LOTS/T5.md) | Traiter un document contenant des instructions adverses et du contenu actif | Données interprétées comme non fiables ; aucune exécution ni modification des politiques ; traitements restreints. |
| AC-T5-07 | [T5.7](LOTS/T5.md) | Appeler l’API serveur sans authentification, avec frontend désinstallé | Accès refusé ; sessions/autorisations et HTTPS distant restent exigés indépendamment du frontend. |
| AC-T5-08 | [T5.8](LOTS/T5.md) | Désactiver une méthode de collecte ou modifier une restriction | Le contrôleur bloque/suspend les opérations concernées ; ni connecteur ni IA ne contournent la règle. |
| AC-T5-09 | [T5.9](LOTS/T5.md) | Modifier une permission et déclencher un blocage | Audit sécurité distinct, protégé et sans secrets ; rétention configurable et historique pertinent consultable. |
| AC-T6-01 | [T6.1](LOTS/T6.md) | Charger et parcourir un réseau à plusieurs niveaux | Graphe logique PostgreSQL indexé ; aucune base graphe spécialisée obligatoire. |
| AC-T6-02 | [T6.2](LOTS/T6.md) | Ajouter un type d’entité et plusieurs identifiants externes | Identifiant interne stable, types extensibles/versionnables ; identifiants externes distincts. |
| AC-T6-03 | [T6.3](LOTS/T6.md) | Créer deux relations datées entre les mêmes entités | Types, direction éventuelle, périodes, preuves et statuts préservés ; corrélation non convertie en lien juridique. |
| AC-T6-04 | [T6.4](LOTS/T6.md) | Rapprocher deux homonymes partageant une adresse | Proposition justifiée et incertitude conservée ; aucune fusion sur ces seuls indices. |
| AC-T6-05 | [T6.5](LOTS/T6.md) | Fusionner après validation puis annuler avec de nouvelles connaissances | Originaux et historique conservés ; dépendances réévaluées ; correspondances certaines automatisables seulement selon règles explicites. |
| AC-T6-06 | [T6.6](LOTS/T6.md) | Recevoir des assertions concurrentes à dates différentes ou identiques | Temporalités analysées, contradictions réelles signalées, aucune version effacée arbitrairement. |
| AC-T6-07 | [T6.7](LOTS/T6.md) | Afficher une hypothèse acceptée par l’utilisateur | Nature, étayage et décision humaine restent distincts ; confiance explicable, pas de score opaque de vérité. |
| AC-T6-08 | [T6.8](LOTS/T6.md) | Partager une entité entre deux branches puis rejeter localement sa pertinence | Référentiel commun conservé ; décision locale non propagée comme vérité globale ; impacts factuels ciblés. |
| AC-T6-09 | [T6.9](LOTS/T6.md) | Explorer une entité à connectivité élevée | Chargement progressif, limites et recalcul ciblé maintiennent une vue exploitable et les budgets. |
| AC-T7-01 | [T7.1](LOTS/T7.md) | Exporter un dossier puis l’importer sur une autre installation compatible | Conteneur documenté ZIP64, données JSON/JSONL et pièces ; versions et dépendances permettent restitution sans IA. |
| AC-T7-02 | [T7.2](LOTS/T7.md) | Altérer ou supprimer une pièce de l’archive | Empreintes/manifeste détectent l’écart avant restauration ; diagnostic ; aucune prétention de signature auteur par SHA-256. |
| AC-T7-03 | [T7.3](LOTS/T7.md) | Exporter chiffré, tenter lecture sans phrase secrète et altérer l’enveloppe | Contenus et métadonnées sensibles protégés ; authentification cryptographique vérifiée ; dérivation Argon2id ; restitution hors ligne avec la bonne clé. |
| AC-T7-04 | [T7.4](LOTS/T7.md) | Exclure une pièce nécessaire à une conclusion | Aperçu reflète le périmètre réel, exclusion effective et avertissement de chaîne de preuve partielle. |
| AC-T7-05 | [T7.5](LOTS/T7.md) | Ouvrir le rapport HTML avec le réseau bloqué | Synthèse/graphe/détails disponibles selon le périmètre inclus ; aucun appel automatique ni script de source exécuté. |
| AC-T7-06 | [T7.6](LOTS/T7.md) | Importer une archive en conflit avec un dossier existant | Aperçu, résolution supervisée et application cohérente ; aucun écrasement silencieux ; aucun lancement de recherche. |
| AC-T7-07 | [T7.7](LOTS/T7.md) | Importer une version ancienne compatible puis une version inconnue | Migration documentée et conservatrice dans le premier cas ; refus clair et sans dommage dans le second. |
| AC-T7-08 | [T7.8](LOTS/T7.md) | Relire la trace d’un export sélectif | Date, type, périmètre, exclusions et intégrité disponibles ; aucun secret ou phrase de chiffrement exposé. |
| AC-T7-09 | [T7.9](LOTS/T7.md) | Comparer restauration d’archive et restauration d’installation | La documentation et les commandes distinguent le dossier portable de la sauvegarde complète PostgreSQL/configuration/fichiers. |
| AC-T8-01 | [T8.1](LOTS/T8.md) | Appeler un modèle cloud puis local depuis plusieurs composants | Courtier unique pour capacités, paramètres, politiques et coûts ; aucune voie directe non supervisée. |
| AC-T8-02 | [T8.2](LOTS/T8.md) | Affecter toutes les fonctions IA à un seul modèle | Planification/extraction/analyse/synthèse restent des rôles ; plusieurs agents autonomes ne sont pas obligatoires. |
| AC-T8-03 | [T8.3](LOTS/T8.md) | Router une tâche simple et une tâche exigeante | Choix compatible avec qualité, coût, disponibilité, préférences, données autorisées et budget ; aucune baisse silencieuse de qualité. |
| AC-T8-04 | [T8.4](LOTS/T8.md) | Concurrence, timeout, réessai et facture finale divergent de l’estimation | Réservations et réconciliation durables couvrent tous les niveaux ; aucun nouvel engagement non autorisé ; écarts visibles. |
| AC-T8-05 | [T8.5](LOTS/T8.md) | Répéter une analyse compatible puis changer son contexte | Réutilisation possible seulement si pertinente ; invalidation adaptée ; traçabilité conservée et qualité non dégradée silencieusement. |
| AC-T8-06 | [T8.6](LOTS/T8.md) | Recevoir une réponse IA malformée ou à références invalides | Schéma et références contrôlés avant usage métier ; rejet/correction contrôlée ; réessai soumis aux limites. |
| AC-T8-07 | [T8.7](LOTS/T8.md) | Examiner une affirmation générée | Entrées, modèle/version disponible, paramètres, sortie et preuves retracés ; hypothèse non promue automatiquement en fait. |
| AC-T8-08 | [T8.8](LOTS/T8.md) | Proposer l’envoi de données sensibles à un nouveau fournisseur | Minimisation et règles de transmission appliquées ; aucun secret dans prompt ; autorisation spécifique si requise. |
| AC-T8-09 | [T8.9](LOTS/T8.md) | Rendre le fournisseur principal indisponible | Repli seulement vers alternative autorisée pour données et coût ; sinon attente/échec exploitable, résultats accessibles. |
| AC-T8-10 | [T8.10](LOTS/T8.md) | Comparer deux configurations modèles sur un jeu d’essai | Critères par tâche, résultats, erreurs, latence et coûts mesurés de façon reproductible, indépendamment du fournisseur. |

## 4. Scénarios de cohérence transversale

| ID | Références | Déclencheur | Résultat attendu |
| --- | --- | --- | --- |
| REC-X-01 | A.1, C2-01 | Lancer avec indices et sans objectif | Le mode exploratoire démarre sous limites admissibles ; aucun objectif obligatoire ajouté par l’UI. |
| REC-X-02 | A1, C7, T4.3 | Exécuter un rebond puis demander un approfondissement distinct | Le rebond interne suit l’autorisation existante ; l’approfondissement crée une branche après action explicite. |
| REC-X-03 | A11, C3-06, C6-15 | Corriger une identité après stabilisation d’un rapport | Impacts locaux recalculés ; rapport marqué à actualiser, version conservée et régénération sur demande. |
| REC-X-04 | A §16, D1, T2.1, T3.11 | Ouvrir une investigation depuis deux clients du même backend | État métier et enveloppes proviennent du backend ; aucun plafond financier propre au navigateur faisant autorité. |
| REC-X-05 | A §16, D6, T5.7 | Utiliser l’installation sans compte cloud puis accéder au mode serveur | L’usage local ne requiert pas de service cloud ; le serveur exige une authentification. |
| REC-X-06 | C7-18, D1, D5, T2.5 | Clôturer une recherche avec programmation de sauvegarde désactivée | État enregistré ; aucun export automatique ; sauvegarde manuelle possible ; programmation activable volontairement. |
| REC-X-07 | D4, T2.8, T6.8 | Supprimer un dossier partageant une preuve avec un autre | Analyse des dépendances préserve le dossier restant ; purge du cache sans disparition d’éléments probants. |
| REC-X-08 | A.7, C3-05, D3, T8.4 | Atteindre le budget avant une génération finale de synthèse | Aucun appel hors budget ; résultats et dernière synthèse disponibles, avec limite explicite. |
| REC-X-09 | D7, T8.4 | Réduire un plafond global pendant une investigation | Nouvelles opérations incompatibles bloquées ; instantané historique et dépenses existantes inchangés. |
| REC-X-10 | D5, T7.5 | Exclure des données sensibles puis ouvrir HTML et inspecter les contenus embarqués | Données absentes aussi des JSON/scripts/pièces embarqués ; aucun chargement externe automatique. |
| REC-X-11 | D7, T3.6, T4.7 | Arrêter localement un appel dont le fournisseur ne confirme pas l’état | Statut incertain et réservation traités selon réconciliation ; aucune relance aveugle ni budget supposé libéré. |
| REC-X-12 | A §20, D7, T4.7 | Redémarrer après crash puis consulter un ancien dossier | Reprise contrôlée de l’opération interrompue ; consultation possible ; aucune surveillance périodique d’ancien dossier activée implicitement. |

## 5. Vérifications et mise en œuvre
Utiliser des jeux locaux et des substituts pour sources/IA afin de simuler coût, quotas, erreurs, délais, schémas invalides, injections, contradictions et interruptions sans dépense. Des tests de contrat externes peuvent compléter ce socle dans une enveloppe et une politique de transmission autorisées.
Les critères de performance restent qualitatifs tant que volumes, matériel et seuils mesurables ne sont pas spécifiés. C exige une représentation exploitable avec plusieurs centaines d’entités ; ne pas inventer un engagement de latence ou de débit.
Les tests de restauration doivent vérifier le contenu restitué et ses liens de provenance, pas seulement la réussite de la commande. Les tests de chiffrement et d’exclusions doivent inspecter les métadonnées et les données réellement présentes. Les tests financiers portent sur les interleavings concurrents et la reprise, pas seulement sur un compteur séquentiel.
La matrice de décisions est dans [DECISIONS.md](../COWORKAI/DECISIONS.md). Les 96 règles détaillées d’interface et les thèmes A.1–A.13 restent applicables au-delà de ces scénarios représentatifs.
