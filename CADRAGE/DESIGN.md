# OSIA — Cadre UX et conception visuelle

**Édition 1.1 — 06/11/2026.** Obligations fonctionnelles acquises ; charte graphique et maquettes détaillées non arbitrées.

## Exigences déjà décidées

- Page principale unifiée, indices et objectif facultatif en haut ; suivi puis synthèse, graphe et fiches. Pas d'assistant multipage imposé au lancement.
- Paramètres avancés repliables ; accès central aux paramètres globaux. Le contexte et la position du graphe sont préservés à l'ouverture des détails.
- Panneaux contextuels fermables, redimensionnables/épinglables selon pertinence ; adaptation aux petits écrans.
- Suivi des opérations et de la consommation disponible sans faux pourcentage ni montant exact inventé.
- Navigation depuis une conclusion vers relations, entités, preuves et dates.
- Graphe réseau, vue des parcours et regroupements ; zoom, déplacement, fixation des nœuds, recherche, filtres et affichage progressif.
- Liens documentés continus, hypothétiques discontinus ; contradictions distinctes ; les conventions ne doivent pas donner à une hypothèse l'apparence d'un fait.
- Arbre des branches séparé sémantiquement du graphe relationnel. Vues par branche et consolidée ; éléments masqués distinguables des éléments absents.
- Deux statuts distincts : étayage documentaire et décision humaine. Historique factuel séparé de l'historique des opérations OSIA.
- Rapports consultables avant export ; aperçu du périmètre et exclusions réelles ; paramètres et budget visibles avant approfondissement.
- Une synthèse stabilisée devenue obsolète est signalée ; son actualisation est demandée explicitement.

Les détails exhaustifs sont les 96 règles C1-01 à C7-20 réparties dans [C.md](LOTS/C.md), complétées par A, D et T7. Ces plages ne constituent pas une numérotation continue unique.

## Travail de conception encore nécessaire

| Livrable | Contraintes à préserver |
| --- | --- |
| Maquettes des états vide, actif, limité, arrêté et erreur | Même espace ; résultats partiels et motif d'arrêt disponibles |
| Charte graphique et composants | Aucune police, couleur de marque, dimension fixe ou framework n'est imposé ici |
| Panneaux, modale de paramètres et responsive | Lisibilité et maintien du contexte ; paramètres centraux et réglages par investigation distincts |
| Accessibilité et interactions clavier | Critères et niveau cible à spécifier ; ne pas annoncer une conformité non vérifiée |
| Vues de confiance et contradictions | Dimensions explicables ; pas de pourcentage non calibré |
| États de configuration et sécurité | Modes, modules, activation des fournisseurs, permissions et coûts compréhensibles |
| Export HTML | Lecture seule, hors ligne, sélection/exclusions effectives et aucune requête automatique |

Les exemples de Roadbook, Relia ou d'autres projets ne constituent pas une charte OSIA. Le futur client GNOME est distinct et différé ; il ne doit pas dicter une dépendance native au frontend web initial.
