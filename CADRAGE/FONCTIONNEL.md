# OSIA — Vue fonctionnelle consolidée

**Édition 1.1 — 06/11/2026.** Vue transversale ; [les lots détaillés](README.md) conservent leurs exigences et critères.

## 1. Finalité et parcours

OSIA répond à une question ou explore des indices à partir de sources publiques. L'objectif est facultatif et oriente la recherche ; une affirmation orientée est traitée comme une hypothèse à vérifier. Le moteur peut décomposer la question en sous-objectifs et réviser son plan.

L'utilisateur saisit les indices et, s'il le souhaite, un objectif, choisit des limites admissibles puis lance l'investigation. Ce lancement peut matérialiser l'acceptation des paramètres visibles ; aucun écran supplémentaire d'approbation ni validation à chaque rebond ne sont imposés. Une ambiguïté réellement bloquante peut demander une clarification.

La recherche initiale est le niveau 0. Chaque nouvelle génération d'exploration est un rebond ; plusieurs appels peuvent appartenir au même niveau. La profondeur maximale de 1 à 10 est un plafond, pas un objectif de consommation. Les tâches et pistes internes se déploient automatiquement sous les limites déjà accordées. Une **branche d'approfondissement** est un nouvel espace lié, avec objectif et limites propres, lancé explicitement par l'utilisateur ; elle ne doit pas être confondue avec une simple ramification interne du plan.

Sources : A.1, A.5–A.7, A.12 ; B4 ; C2, C7 ; D3 ; T4.

## 2. Pistes, arrêt et prolongation

Les pistes sont évaluées selon pertinence, fiabilité, nouveauté, potentiel, fraîcheur et coût. Les pistes secondaires restent consultables sans être automatiquement approfondies. Les contraintes d'accès et de budget sont bloquantes, indépendamment du score de priorité.

Dès que la réponse est suffisamment étayée, le moteur cesse l'exploration, restitue les acquis et propose les suites pertinentes sans les exécuter. Les autres arrêts incluent limites de profondeur, budget, ressources, absence de piste utile, indisponibilité, erreur, sécurité et interruption humaine. Les résultats partiels sont conservés.

| Dimension | Valeurs ou sens |
| --- | --- |
| Qualité de réponse | Étayée, partielle ou indéterminée |
| Motif d'arrêt | Objectif atteint, limite, interruption, pistes épuisées, source indisponible, etc. |
| État de travail | Non lancé, actif, suspendu/interrompu, arrêté/terminé ou erreur selon la machine à états à spécifier |

Une prolongation crée une branche liée avec nouveaux paramètres explicitement acceptés. Sa profondeur repart de son propre point de départ ; les plafonds de l'investigation et du mois restent applicables. Ni création de branche, ni correction, ni import ne réinitialisent les dépenses.

Sources : A5, A.7–A.9, A.12 ; B4 ; C7 ; D3 ; T4.3–T4.8.

## 3. Connaissances et preuves

Entités, références, assertions, relations, observations, analyses IA et décisions humaines restent distinctes. Une identité commune et une relation entre deux entités sont deux questions différentes. Une même adresse, un nom similaire ou un code d'activité commun ne prouvent pas une affiliation ni une identité.

Chaque assertion importante renvoie à ses sources, à la méthode de collecte, à la date de consultation et à la date/période du fait lorsqu'elle est connue. Les contenus originaux ou extraits conservables sont préservés ; une référence seule ne devient pas une copie de preuve et les limites de conservation sont explicites.

Les contradictions et versions historiques restent visibles. Des sites répétant une même source ne constituent pas automatiquement des corroborations indépendantes. L'absence de résultat ne prouve pas l'inexistence d'un fait.

| Dimension indépendante | Exemples |
| --- | --- |
| Nature de l'énoncé | Information rapportée, fait documenté, indice, hypothèse, conclusion analytique |
| Étayage | Documenté, corroboré, à confirmer, contradictoire, non établi |
| Décision humaine | Non examiné, validé, rejeté |
| Pertinence | Contribution à l'objectif d'une branche |
| Temporalité | Période de validité du fait ; date de collecte distincte |

La confiance repose sur des dimensions explicables. Pas de probabilité chiffrée présentée comme fiable sans calibration défendable. Les termes ci-dessus ne forment pas un unique enum technique ; le schéma sera conçu en préservant ces distinctions.

Sources : A.3–A.4, A.8 ; B5 ; C3, C5, C6 ; D4 ; T6.

## 4. Corrections, partage et synthèses

Valider, rejeter, corriger, annoter, rapprocher, fusionner, séparer et annuler sont des actions traçables. Les fusions ambiguës demandent validation humaine ; seules les correspondances techniques certaines peuvent être automatisées selon des règles explicites. L'annulation réévalue les dépendances sur les connaissances actuelles, sans restaurer aveuglément une conclusion ancienne.

Une correction factuelle d'identité s'applique aux contextes réellement dépendants de cette identité. Un rejet de pertinence reste propre à sa branche. Le référentiel commun entre branches et investigations ne mélange pas leurs objectifs, conclusions, permissions ou historiques.

Pendant une recherche active, une synthèse provisoire peut évoluer après une découverte significative, dans le budget autorisé. À l'arrêt, la synthèse est stabilisée. Une découverte ultérieure ou une correction la rend, si nécessaire, **à actualiser** ; la régénération se fait sur demande et conserve les versions pertinentes. Aucune branche clôturée ne redémarre automatiquement.

Sources : A9–A12 ; C3-04–06, C6, C7 ; D4 ; T6.5–T6.8.

## 5. Interface et restitution

Une page principale rassemble saisie, suivi, synthèse, graphe et accès aux fiches. Les détails sont contextuels ; les panneaux peuvent être fermés, redimensionnés ou épinglés selon pertinence. L'interface s'adapte aux petits écrans. Le menu central de paramètres regroupe la configuration ; ses détails visuels restent à concevoir.

L'ordre de restitution est synthèse courte, graphe, fiches et preuves, avec navigation libre entre ces éléments. Le suivi montre les opérations et consommations disponibles sans faux pourcentage. Les coûts estimés, réservés, constatés et disponibles ne sont pas confondus.

Le graphe relationnel décrit les liens entre entités ; l'arbre des investigations décrit les approfondissements ; la vue arborescente des parcours décrit les chemins d'exploration. Aucun de ces liens de navigation ne vaut preuve d'une relation factuelle. Filtres, masquage, regroupements et positions de nœuds ne modifient pas les faits.

Les rapports synthétiques et dossiers détaillés sont consultables avant export, par branche ou en vue consolidée. Les 96 règles détaillées du lot C s'appliquent. Voir [DESIGN.md](DESIGN.md).

## 6. Configuration, sources et IA

Les sources configurées, disponibles et autorisées sont activées par défaut, désactivables individuellement ; une source activée n'est pas forcément interrogée. Le catalogue est généraliste et international, extensible par contrat commun. Les sept familles de B2 ne valent pas engagement d'intégrer tous les services cités.

Les accès API, web, documents, données ouvertes et navigateur avancé sont sélectionnés selon les besoins et autorisations. L'authentification autorisée à un service ne permet pas de contourner des protections ou de transformer le produit en outil d'accès aux espaces privés.

Les fournisseurs et modèles IA sont configurables, par rôle ou avec un modèle unique. Les alternatives doivent être autorisées pour la transmission et le coût. Les clés ne persistent pas par défaut ; coffre chiffré facultatif. Les paramètres suivent global → profil → investigation → branche ; les plafonds supérieurs et nouvelles restrictions globales restent opposables aux opérations futures.

Sources : B1–B7 ; D2, D3, D7 ; T3.9–T3.11 ; T5 ; T8.

## 7. Conservation, portabilité et suppression

| Mécanisme | Finalité | Déclenchement |
| --- | --- | --- |
| Persistance de travail | État durable et reprise contrôlée | Enregistrement progressif automatique |
| Sauvegarde technique | Continuité de l'installation, base et fichiers cohérents | Manuelle ; programmation facultative |
| Archive `.osia` | Export logique, échange et restauration de dossiers | Manuel, sélectif, chiffrable |
| HTML autonome | Consultation interactive en lecture seule, hors ligne | Manuel ; export combiné possible |

Les données exclues d'un export doivent être absentes de ses contenus, pas simplement cachées. Aucun secret dans les archives, rapports ou exports de configuration. Un rapport n'effectue aucun appel automatique au réseau ; les liens externes demandent une action volontaire. L'import vérifie format, intégrité, compatibilité et conflits avant modification ; il ne relance pas de recherche.

Le dossier conservé n'expire pas automatiquement par défaut. Le cache est purgeable seulement s'il n'est pas nécessaire aux preuves et décisions conservées. Archiver, supprimer un dossier et effacer toutes les données ont des portées distinctes ; les suppressions contrôlent les dépendances partagées. Les contraintes de conservation applicables restent prises en compte.

Sources : D1, D4–D7 ; T2 ; T7.

## 8. Limites du périmètre

Local signifie sur l'hôte Linux choisi, poste ou serveur, sans service cloud OSIA imposé. Les appels aux sources et modèles distants autorisés peuvent transmettre les données nécessaires. L'usage du mode serveur exige une authentification, même sans frontend web.

Le client GNOME est ultérieur ; la surveillance automatisée des anciennes investigations est une piste V2. Le catalogue précis, les seuils, la charte visuelle et la liste exhaustive des fonctions V1 ne sont pas inventés ici. Voir [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md).
