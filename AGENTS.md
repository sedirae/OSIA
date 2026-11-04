# Instructions communes aux agents IA

**Statut :** règles générales du projet, à adapter lors de son initialisation.  
**Périmètre :** tout le dépôt, sauf instructions plus spécifiques explicitement validées.  
**Objectif :** permettre à plusieurs agents et humains de collaborer sur une base documentaire et technique vérifiable.

## 1. Démarrage et contexte

1. Lire ce fichier, puis le `README.md` du projet.
2. Consulter **uniquement les références pertinentes** : `CADRAGE/README.md` pour les décisions applicables, `roadmap/README.md` pour les fonctionnalités, `COWORKAI/README.md` pour les travaux en cours.
3. **Lors de l'initialisation d'un projet, d'une évolution fonctionnelle à cadrer ou d'une révision documentaire demandée**, appliquer [PROJECT-INIT.md](PROJECT-INIT.md). Ne pas le relire lors de chaque petite intervention de code.
4. Ne pas supposer avoir accès à des échanges antérieurs, d'autres IA ou des outils qui ne sont pas effectivement disponibles.

## 2. Répartition des responsabilités documentaires

- **`AGENTS.md`** : règles stables de travail, autonomie, sécurité, validation et escalade.
- **`CADRAGE/`** : besoins, choix métier, techniques et design **applicables**.
- **`roadmap/`** : spécifications autonomes des fonctionnalités à réaliser.
- **`COWORKAI/`** : missions, arbitrages significatifs, constats, tests, revues, blocages et passations.
- **Git, PR et CI** : historique du code et preuves d'exécution ; éviter de les recopier dans un journal manuel.

Lorsqu'une décision durable évolue, actualiser sa **source de vérité dans CADRAGE** et les spécifications affectées ; tracer la décision importante dans `COWORKAI/DECISIONS.md`. Un journal vivant ne remplace pas le cadrage.

Les statuts documentaires sont : **`VALIDÉ`, `PROPOSÉ`, `OUVERT`, `REPORTÉ`, `REMPLACÉ`**. Une proposition d'agent n'est jamais une décision validée par défaut. En cas de contradiction, identifier les sources et demander l'arbitrage structurant plutôt que choisir arbitrairement.

## 3. Autonomie et limites

**Agir sans validation supplémentaire** pour les opérations ordinaires, réversibles et cohérentes avec la mission : lecture du code, édition sur branche dédiée, tests locaux, vérification statique, correction de défauts dans le périmètre autorisé, documentation et rapport.

**Demander une autorisation explicite** avant :
- Fusion dans la branche principale ou publication/déploiement de production.
- Modification destructive de données réelles, migration risquée ou changement de secrets/permissions de production.
- Création d'une ressource facturable, engagement de dépense ou exposition publique d'un dépôt/service.
- Changement de règle métier, de périmètre ou de choix technique structurant non validé.
- Modification de règles d'accès ou publication d'informations sensibles non prévue au cadrage.

Respecter les protections du dépôt, le principe du moindre privilège et les politiques du fournisseur de services. Ne jamais ajouter de secrets dans le code, les rapports ou les commits.

## 4. Escalade

| Situation | Comportement attendu |
| --- | --- |
| Détail technique courant et réversible | Trancher et documenter brièvement si utile |
| Hypothèse secondaire incertaine | Marquer `PROPOSÉ`, ne pas la présenter comme un accord |
| Erreur, échec de test, problème de compilation | Reproduire, diagnostiquer, corriger dans le périmètre ; noter les limites |
| Domaine nécessitant un autre spécialiste ou modèle | Déléguer ou demander une revue **uniquement si le moyen existe réellement** |
| Avis techniques contradictoires | Comparer les preuves, tenter de résoudre, puis escalader si l'arbitrage reste structurant |
| Règle métier, coût, sécurité, architecture irréversible | Solliciter l'utilisateur avec des options et leurs conséquences |

Regrouper les questions bloquantes. **Ne pas demander une confirmation pour chaque commande ou test** autorisé. Une escalade réelle et sa résolution sont consignées dans `COWORKAI/` si cela aide la passation.

## 5. Git, livraisons et rapports

1. Travailler sur une **branche dédiée** à une mission ou modification cohérente ; ne pas écrire directement dans `main` sauf instruction explicite.
2. Préserver l'existant et éviter les modifications hors périmètre. Ne jamais écraser intentionnellement le travail d'un autre agent.
3. Exécuter les vérifications réellement possibles, indiquer leur commande, leur environnement, leur résultat et les tests non exécutés.
4. Référencer les commits ou SHA effectivement testés, les PR et les exigences couvertes. Signaler les limitations et la recette manuelle restante.
5. Produire une **PR** avec le contexte, les modifications, les tests et les risques ; laisser la décision de fusion à l'utilisateur.
6. Préparer la transmission dans `COWORKAI/rapports/` si la mission est suffisamment importante ; privilégier un rapport bref et vérifiable à un journal de chaque action.

**Code livré ≠ tests validés ≠ revue validée ≠ fusionné ≠ déployé.** Les statuts ne progressent que sur preuves ; un agent/relecteur peut rétrograder ou rouvrir une mission en présence d'une régression justifiée, sans effacer l'historique.

## 6. Personnalisation lors de l'initialisation

Adapter cette section uniquement aux conventions **validées** du nouveau projet :

- Commandes de test et de qualité : **à renseigner**.
- Référence de branche principale et stratégie de PR : **à confirmer**.
- Environnements autorisés et interdits : **à renseigner**.
- Particularités de confidentialité ou de sécurité : **à renseigner**.

Les éléments « à renseigner » ne constituent ni une autorisation, ni une validation implicite.
