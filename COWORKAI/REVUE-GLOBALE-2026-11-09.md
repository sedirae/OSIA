# Revue globale de robustesse — 9 novembre 2026

## Périmètre et résultat

Revue du moteur, API, paramètres IA, frontend, installation, stockage, imports/exports,
sauvegardes, politiques et coûts. Base : `main` à `a8772bc`, avec les PR #29
(`887900c`) et #30 (`12463d2`) combinées dans une branche de travail. Aucune fusion
dans `main`. La branche de revue contient ces deux prérequis et les correctifs ci-dessous.

Les 272 tests existants passent sur la combinaison initiale. Cela ne suffisait pas :
24 nouveaux scénarios ont d’abord échoué sur huit familles de défauts. Les scénarios
complémentaires couvrent ensuite concurrence, rollback financier, requêtes hostiles,
archives chiffrées et échec d’installation. Les fournisseurs et sources sont simulés ;
aucun appel IA facturable n’a été réalisé.

## Défauts corrigés

| Réf. | Priorité | Déclencheur et effet avant correction | Correction et preuve |
| --- | --- | --- | --- |
| G01 | P1 | `OSIA_MODE=Server` ou une autre faute contournait à la fois les règles Desktop et Server. | Refus de tout mode inconnu, port invalide ou paire TLS incomplète avant lancement. Tests de configuration. |
| G02 | P1 | Le service Desktop sans jeton acceptait un `Host` arbitraire et une origine tierce ; la boucle locale seule ne protège pas du rebinding DNS. | Vérification du Host local et de l’Origin. Tests API de refus et accès légitime. |
| G03 | P1 | Un deuxième moteur exécutait `recover()` sur les tâches du premier avant même de découvrir le port HTTP occupé. | Verrou PostgreSQL conservé pendant la vie de l’ordonnanceur, refus du second moteur avant récupération. Test avec une tâche réellement en cours. La santé signale aussi un ordonnanceur arrêté. |
| G04 | P2 | Deux initialisations pouvaient rejouer le même DDL ; une erreur de démarrage pouvait laisser le pool ouvert. | Migrations sérialisées dans une transaction, fermeture sur échec, arrêt couvert par `finally`. Test de trois migrations simultanées sur base vide. |
| G05 | P2 | Durée des sessions, rétention d’audit et désactivation des connecteurs étaient perdues ou ignorées après redémarrage. | Restauration des valeurs persistées et persistance des bascules de connecteurs. Test avec une nouvelle instance du moteur. |
| G06 | P1 | Un usage IA vide/incomplet devenait un coût nul ; une mauvaise forme pouvait lever pendant le bilan. | Compteurs entiers non négatifs et complets exigés ; sinon coût incertain et réservation conservée. Huit réponses fournisseur malformées testées via le courtier. |
| G07 | P1 | État d’opération et consommation/libération pouvaient être écrits dans des transactions différentes ; une réservation tardive ressuscitait une opération annulée. | Écriture du registre et état dans la même transaction ; rattachement conditionnel de la réservation. Tests d’incident après écriture et d’arrêt pendant réservation. |
| G08 | P2 | `stop` et `revalidate` prenaient les verrous dans un ordre inverse ; `resume` utilisait un état lu avant attente. | Ordre investigation → opération ; état et incertitudes relus sous verrou à la reprise. Tests de concurrence. |
| G09 | P2 | JSON d’import invalide, archive inaccessible, entrée de manifeste scalaire ou identifiant absent produisaient des erreurs internes ; upload chargé intégralement en mémoire. | Erreurs métier 400/422, lecture d’upload par blocs avec plafond 512 Mio, nettoyage et fermeture sur erreur, validation du manifeste et des identifiants. Tests d’archives et de flux trop gros. |
| G10 | P2 | L’interface affichait « Import appliqué » après une réponse 422 ; un secret d’import pouvait être placé dans l’URL ; le formulaire ne permettait pas les archives chiffrées. | Contrôle du statut, prévisualisation requise, champ de phrase secrète, en-tête dédié pour l’upload. Tests API et recette Chromium. |
| G11 | P2 | Une réponse lente remplaçait la nouvelle page ; le flux SSE continuait après navigation ; la déconnexion laissait les données affichées. | Invalidation des réponses périmées, annulation du suivi, effacement de la vue/session, temporisation à la fermeture du flux. Recette Chromium et smoke JS. |
| G12 | P2 | Deux requêtes identiques avec des paramètres différents partageaient le cache ; une synthèse de branche recevait l’objectif parent. | Clé de cache versionnée incluant les paramètres, objectif propre à la branche. Tests du pipeline source et du contexte de synthèse. |
| G13 | P2 | Un téléchargement pip raté laissait un venv qui bloquait toute nouvelle tentative. | Suppression du seul venv créé par la tentative en échec, avant toute création de base ; autres fichiers conservés. Test de deux tentatives consécutives. |

Les changements se rattachent à EXEC-02/03/05, T2.4, T3.6/11/14, T4.3/7,
T5.4/7, T7.2/6, T8.4/5 et D7. Aucun changement du périmètre produit n’est déduit
de la seule présence de tests.

## Vérifications et limites

- Suite locale finale au moment de cette rédaction : **307 réussis, 1 ignoré**.
- Le test ignoré est exclusivement la recette Chromium : le navigateur échoue ici à
  créer son socket Unix (`Operation not permitted`). La CI installe Chromium et rend
  cette recette obligatoire avec `OSIA_BROWSER_TESTS=1`.
- PostgreSQL réel en local via TCP, migrations, sauvegardes, imports, concurrence et
  démarrage HTTP. Le fixture PostgreSQL de cet environnement utilise un transport TCP
  temporaire ; les tests du dépôt et de la CI utilisent le fixture normal.
- La recette navigateur vérifie : authentification Server, saisie/enregistrement du
  fournisseur local sans appel, investigation simulée, erreurs d’import, navigation
  pendant une réponse retardée, affichage mobile et déconnexion.
- Pas de qualification d’un fournisseur payant, de panne électrique réelle, de test de
  charge prolongé ni de matrice complète des distributions Linux. Une suite verte ne
  constitue pas une garantie d’absence de défauts.

## Points fonctionnels restant à traiter

Ces points sont identifiés par lecture de code ; ils ne sont pas déclarés corrigés par
les tests ci-dessus et doivent être suivis séparément des corrections de robustesse.

1. **P1 — estimation de coût avant appel.** `AIAdapter.estimate_input_tokens()` utilise
   environ quatre caractères par token. Ce n’est pas une borne supérieure pour du JSON,
   des identifiants ou du texte multilingue. La réservation peut donc sous-estimer le coût,
   même si la consommation réelle est correctement constatée ensuite. Prévoir une estimation
   conservatrice par fournisseur/modèle, plafonner l’entrée et refuser les coûts non bornables.
   Les tarifs saisis doivent aussi correspondre au modèle réellement facturé.
2. **P2 — limites propres aux branches.** Dans `PolicyEngine.authorize()`, les limites de
   branche sont combinées à celles du parent, puis comparées aux compteurs de toute
   l’investigation et à sa date de création. Une branche fraîche peut être refusée à cause
   des opérations ou de l’ancienneté du parent. Séparer les compteurs/délais de chaque portée
   sans réinitialiser les budgets déjà consommés, puis tester une prolongation tardive.
3. **P2 — contexte probant de synthèse.** `_build_synthesis_input()` fournit les métadonnées
   des preuves, les relations avec leurs identifiants et les assertions ; il n’inclut pas
   encore un extrait du texte des preuves ni les libellés des entités. Corriger l’objectif
   de branche ne suffit pas à qualifier la qualité d’une synthèse réelle. Compléter un
   contexte borné et traçable, puis une recette métier sur des preuves connues.

Le choix Playwright comme **connecteur de collecte** reste l’arbitrage déjà documenté
dans RECETTE-APPLICATIVE.md §8. Chromium utilisé ici pour **tester l’interface** ne réalise
pas ce connecteur et ne clôture pas cet écart.

## Compatibilité

- Upload binaire chiffré : phrase UTF-8 encodée en base64 dans
  `X-OSIA-Archive-Passphrase-B64`. Le paramètre URL `passphrase` est refusé ; le corps JSON
  historique `{path, passphrase}` reste accepté. Les secrets ne sont pas recopiés dans
  les erreurs de validation d’import.
- Les anciennes entrées du cache ne sont plus réutilisées : nouvelle clé `v2`, sans
  suppression des preuves conservées.
- Desktop : ouvrir `http://127.0.0.1:8471` ou `localhost`, pas un nom de domaine tiers.
- Un seul ordonnanceur actif par base ; les commandes de lecture restent disponibles.
- Après un échec d’installation **postérieur** à la création de PostgreSQL, les fichiers
  sont conservés pour diagnostic. Aucun effacement automatique d’une base existante.
