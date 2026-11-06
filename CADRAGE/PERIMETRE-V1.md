# OSIA — Périmètre de livraison V1

Les six arbitrages V1.1 à V1.6 ont été validés par le porteur le 6 novembre 2026. Ces identifiants désignent des décisions de cadrage pour la première livraison. Les lots A–D et T1–T8 décrivent la cible et ses garanties. Les spécifications à produire sont suivies dans [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md).

## V1.1 — Fonctions livrées et reports

| Domaine | V1 |
| --- | --- |
| Installation et accès | Installation Linux Desktop et Server. Moteur Python et PostgreSQL, CLI et API. Interface web facultative. Accès serveur authentifié selon T5.7. |
| Investigation | Indices et objectif facultatif, recherche par rebonds, suivi en direct, arrêt sur objectif atteint ou limite et reprise après incident. Les pistes restantes sont proposées. Lancer un approfondissement demande une validation explicite des limites et du budget. |
| Vérification | Graphe d’entités, arbre des branches, fiches sourcées, contradictions visibles, validation, rejet et correction réversibles. Les décisions humaines et l’étayage des faits restent distincts. |
| Restitution | Export et import supervisé `.osia`, chiffrement facultatif des archives, rapport HTML interactif hors ligne. Les règles de sélection et d’exclusion des données de D5 et T7 s’appliquent. |
| Sauvegarde technique | Sauvegarde manuelle cohérente à chaud et restauration. |

Les évolutions comprennent la programmation des sauvegardes, la surveillance automatisée des anciennes investigations, la collaboration multi-utilisateur, les extensions tierces, l’observabilité avancée et la recherche web généraliste. Le client GNOME et les éventuels composants Rust du moteur restent ultérieurs. Le thème sombre relève de la V2. L’ordre et la date de livraison de ces évolutions restent à décider.

## V1.2 — Connecteurs initiaux

| Connecteur | Capacité initiale | Référence |
| --- | --- | --- |
| API Recherche d’entreprises | Retrouver les entreprises et établissements français par adresse, nom ou identifiant. | [Documentation officielle](https://recherche-entreprises.api.gouv.fr/docs/) |
| BODACC | Rechercher les annonces officielles et documenter les événements d’une entreprise. | [Fiche API DILA](https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-civiles-et-commerciales-bodacc) |
| GLEIF | Couverture internationale par LEI et accès aux relations de parenté déclarées lorsqu’elles sont disponibles. | [Documentation GLEIF](https://www.gleif.org/en/lei-data/access-and-use-lei-data) |
| Web par URL | Lire les pages publiques fournies ou découvertes dans l’enquête et leurs PDF textuels. HTTP en premier, puis Playwright isolé si nécessaire et autorisé. | [T5](LOTS/T5.md) |

La découverte de nouvelles URL provient des sources interrogées et des liens accessibles dans ces pages. La recherche par nom dans un moteur généraliste est reportée. CON-08 couvre les conditions d’accès et de conservation, les quotas et la qualification de chaque connecteur.

## V1.3 — Fournisseurs et modèles IA

- **Cloud** — Mistral API, modèle Small 4 `mistral-small-2603` pour la planification, l’extraction et la synthèse. [Fiche du modèle](https://docs.mistral.ai/models/mistral-small-4-0-26-03)
- **Local** — Adaptateur compatible OpenAI et modèle configuré par l’utilisateur. Ministral 3 8B est le premier candidat à qualifier. [Fiche du modèle](https://docs.mistral.ai/fr/models/ministral-3-8b-25-12)
- **Contrôles** — Le courtier centralise les appels et le moteur valide les réponses structurées. Un repli du local vers le cloud exige une autorisation de transmission et une enveloppe de dépense. Les garanties de T8 s’appliquent à chaque appel.

## V1.4 — Profils, limites et arrêt

| Profil | Rebonds max. | Requêtes source max. | Appels IA max. | Durée max. | Plafond présaisi après activation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rapide (présélectionné) | 2 | 12 | 4 | 2 min | 0,05 € |
| Standard | 4 | 40 | 12 | 10 min | 0,20 € |
| Approfondi | 8 | 100 | 30 | 30 min | 1 € |

Le budget autorisé au premier démarrage est de **0 €**. À l’activation des appels payants, le plafond global présaisi est de **5 €/mois** et s’applique en plus du plafond par investigation. Les montants présaisis sont soumis à l’autorisation de l’utilisateur. Les limites D3/D7 et les réservations T8.4 s’appliquent, y compris aux branches, replis et nouvelles tentatives. La profondeur reste réglable de 1 à 10 rebonds.

Par défaut, deux opérations externes peuvent s’exécuter simultanément. Le délai maximal est de 15 s par requête HTTP et de 60 s par appel IA. Le cache de requêtes expire au bout de 24 h ou plus tôt selon les règles de la source. Les preuves versées au dossier suivent leur propre politique de conservation.

Le moteur peut déclarer l’objectif suffisamment étayé lorsque chaque réponse décisive repose sur une source primaire qui l’établit directement ou sur deux sources indépendantes concordantes, et qu’aucune contradiction majeure ne reste irrésolue. Une adresse ou un code APE partagé constitue un indice. Les autres motifs d’arrêt et la restitution de résultats partiels suivent le lot A.

## V1.5 — Interopérabilité

- **Archive `.osia`** — Conteneur ZIP64, manifeste `manifest.json`, données métier JSON/JSONL et pièces exportables. Le manifeste indique `format_version: "1.0"`, le périmètre, les exclusions et les empreintes SHA-256 des fichiers exportés. L’import présente les conflits avant écriture. Quand le chiffrement est activé, il protège aussi le manifeste. Les schémas, migrations et règles de collision relèvent de CON-14. Le profil et l’enveloppe cryptographiques relèvent de CON-15.
- **API REST** — Préfixe `/api/v1` et contrat OpenAPI. Les évolutions compatibles restent dans `v1`. Une rupture de compatibilité crée une nouvelle version majeure.
- **SSE et commandes** — Identifiants d’événements, reprise par curseur et resynchronisation de l’état si l’historique nécessaire manque. Clé d’idempotence pour le lancement d’une investigation ou d’une branche. Les schémas et règles détaillées relèvent de CON-12.

## V1.6 — Charte visuelle

Thème clair et police système. Fond `#F5F7FA`, surfaces blanches, texte ardoise `#172033` et accent bleu `#2458C6`. Sur grand écran, le graphe occupe le centre et les preuves s’ouvrent dans un panneau latéral. Sur petit écran, les vues s’empilent. Les liens confirmés ont un tracé plein, les hypothèses un tracé pointillé et les contradictions un libellé visible.

La recette vise la navigation clavier, le focus visible et le contraste WCAG 2.2 AA. Les maquettes détaillées relèvent de CON-17. [WCAG 2.2](https://www.w3.org/Translations/WCAG22-fr/)
