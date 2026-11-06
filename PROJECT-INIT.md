# OSIA — Point de départ du projet

**État au 06/11/2026 :** cadrage A–D et T1–T8 clôturé. Référentiel consolidé 1.1 préparé. Aucun état du code existant n'est pris pour acquis.

## Objectif

Construire un outil Linux d'investigation OSINT contrôlable : découverte et recoupement de sources publiques, graphe de connaissances, preuves, corrections humaines, maîtrise des coûts et restitution portable.

## Première séquence de travail

1. Lire [AGENTS.md](AGENTS.md) et [CADRAGE/README.md](CADRAGE/README.md).
2. Établir le périmètre exact de V1 à partir des engagements et exclusions déjà actés dans [CONCEPTION-RESTANTE.md](CADRAGE/CONCEPTION-RESTANTE.md). Ne pas déplacer silencieusement une exigence explicitement initiale vers une version ultérieure.
3. Spécifier les contrats indispensables à la tranche prévue : état d'investigation, politiques et réservations, provenance, API/événements, stockage et reprise.
4. Définir le lot de réalisation, ses dépendances, ses critères de recette et les choix techniques encore nécessaires. Les ordres suggérés de conception ne constituent pas un calendrier validé.
5. Après mandat de développement, implémenter la tranche, vérifier les critères associés et soumettre une PR. La revue doit pouvoir distinguer exigence, choix d'implémentation, code livré et résultat de test.

## Livrables de conception attendus

Contrats et schémas versionnés ; protocole de cohérence base/fichiers ; états et règles de reprise ; politique de sécurité des modes ; contrats des connecteurs et du courtier ; protocole financier ; spécification `.osia` ; maquettes et règles d'accessibilité ; périmètre V1 et étapes de livraison.

Ne pas produire un `requirements.txt` définitif depuis les exemples des anciens documents. Les dépendances et versions découlent de la conception et seront vérifiées au moment de leur sélection.
