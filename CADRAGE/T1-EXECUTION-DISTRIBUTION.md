# OSIA — T1 : Architecture d'exécution et distribution

**Version :** v1.0 — 06/11/2026  
**Statut : VALIDÉ — décisions T1.1 à T1.7**  
**Périmètre :** exécution Linux native, installation, interfaces, communication, maintenance et accès réseau.  
**Source :** arbitrages utilisateur du cadrage technique OSIA, 05–06/11/2026.  
**Document parent :** [TECHNIQUE.md](TECHNIQUE.md) ; les autres sections de conception technique restent PROPOSÉES/OUVERTES.

> Ce document fixe les choix validés du lot T1. Il ne valide pas par extension le langage du cœur, la base de données, le framework HTTP, les mécanismes cryptographiques, ni les lots T2–T8. Les documents fonctionnels A–D v1.0 restent à importer et à confronter à la conception technique.

## 1. Résumé des arbitrages

| ID | Option validée | Décision applicable |
| --- | --- | --- |
| T1.1 | C | Noyau/moteur OSIA local indépendant des interfaces, avec contrat de communication stable. |
| T1.2 | D personnalisée | Linux exclusivement pour exécuter le moteur ; interface web développée en premier ; client natif GNOME/Rust différé. |
| T1.3 | A enrichie | Installation et distribution Linux **natives** ; ni Docker ni Podman requis ou proposés comme mode officiel V1 ; une livraison logicielle unifiée et des composants configurables. |
| T1.4 | C | Mode **poste de travail** (démarrage à la demande) et mode **serveur** (service permanent), sélectionnés lors de la configuration initiale et modifiables ensuite. |
| T1.5 | B | Commandes et lectures par REST ; progression et notifications par SSE. HTTP/3/QUIC compatible à terme, non requis en V1 ; WebTransport non retenu à ce stade. |
| T1.6 | D personnalisée | Installation des mises à jour exclusivement **manuelle**, notification des versions disponibles, migrations contrôlées, sauvegarde et restauration supervisée. |
| T1.7 | D personnalisée | Activation modulaire des interfaces et de l'accès réseau ; API indépendante du serveur de frontend web ; accès distant uniquement sur activation explicite et avec protections. |

## 2. Frontières de l'architecture

### 2.1 Composants

- **OSIA Core** (obligatoire) : moteur d'investigation, orchestration, collecte, politique de coût, données locales, preuves, contrats d'API et flux d'événements. Le cœur ne dépend pas de React ou de GTK.
- **OSIA Web** (facultatif) : frontend React/TypeScript servi au navigateur. Sa désactivation ne désactive **pas** l'API du moteur.
- **OSIA Desktop** (**REPORTÉ**) : client Linux natif Rust, GTK 4, gtk-rs et libadwaita, prioritairement adapté à GNOME ; utilisable avec un moteur local et, à terme, distant. Ce n'est pas une WebView emballant l'interface React.
- **OSIA API** : frontière de communication commune aux clients web et natif. Elle demeure disponible dans les installations « sans frontend web ». Le fait que service HTTP et frontend statique partagent ou non un processus est un détail technique à arrêter ultérieurement.

~~~text
             Navigateur web                 Futur client GTK/Rust
             (V1 local/distant)             (version ultérieure)
                    |                                |
                REST + SSE                      REST + SSE
                    |                                |
                    +---------------+----------------+
                                    |
                         API OSIA — contrôles
                          d'accès et d'origine
                                    |
                           OSIA Core (Linux)
                   orchestration, connecteurs, IA
                                    |
                    base locale, preuves, archives
~~~

Les systèmes Windows, macOS et mobiles ne sont **pas** des plateformes d'exécution native du moteur OSIA. Ils pourront accéder au frontend web via un navigateur autorisé lorsque l'accès réseau aura été configuré.

### 2.2 Modes et disponibilité des interfaces

| Déploiement | Moteur | Frontend web | Client GTK | Statut |
| --- | --- | --- | --- | --- |
| Poste Linux à la demande, interface web locale | Local | Oui | Non | **V1** |
| Serveur Linux permanent, interface web activée | Service | Oui | Non | **V1** |
| Serveur Linux permanent, frontend web désactivé | Service + API | Non | Non | **V1, mode avancé** : API et administration outillée ; avertissement d'absence de GUI native |
| Poste Linux avec client GTK local | Local | Au choix | Oui | **REPORTÉ** |
| Client GTK distant vers serveur sans frontend web | Serveur distant | Au choix | Oui côté client | **REPORTÉ** |

**Règle UX :** en V1, l'assistant ne doit pas suggérer que le client GTK est disponible. Un serveur « API seule » reste installable par un utilisateur avancé, avec avertissement explicite et procédure d'administration documentée. Le frontend web est le chemin principal pour la V1.

## 3. Distribution et assistant de configuration (T1.3, T1.4)

- **Distribution native Linux** en priorité ; format exact et familles de distribution à préciser (paquet Debian comme candidat, **non encore verrouillé**). Aucun conteneur requis pour le déploiement officiel V1.
- **Livraison unifiée :** un seul paquet/distributeur logiciel contenant les composants livrables de la version concernée. L'utilisateur sélectionne les modules à activer/configurer, dont le frontend web.
- **Distinction impérative :** si le livrable est un unique paquet DEB contenant des assets web, le choix « ne pas installer le web » peut signifier « ne pas l'extraire/configurer/servir », mais **pas nécessairement** « les octets web sont absents du paquet ». Toute exigence d'exclusion physique devra être traitée en conception du packaging (sans prétendre que dpkg sélectionne arbitrairement des fichiers au sein d'un même paquet).
- La configuration initiale **pose explicitement la question « Poste de travail ou serveur ? »**, puis propose l'activation du frontend web. Les choix sont modifiables ultérieurement sans perte de données.
- Pour rester compatible avec les installations Linux automatisées, le mécanisme préféré est un assistant réexécutable du type « osia setup », utilisable en interactif et en non-interactif. Sa syntaxe exacte et les mécanismes de paquets ne sont **pas** validés par cette décision.
- Aucun prérequis manuel Docker, Python ou Node.js ne doit être imposé à l'utilisateur final ; les dépendances natives doivent être gérées par les paquets ou le dispositif de livraison.

### 3.1 Mode poste de travail

- Démarrage à la demande et ouverture du navigateur local ; pas de démon système imposé.
- La fermeture d'un onglet ou du navigateur **ne stoppe pas** une investigation.
- Arrêt après inactivité possible **uniquement** sans travail actif et sans opération ambiguë à réconcilier.
- La fermeture de session Linux, un redémarrage ou un arrêt du moteur suspend les traitements de manière contrôlée. Un service utilisateur peut être étudié, sans supposer qu'il survit à la déconnexion.

### 3.2 Mode serveur

- Service de fond permanent, géré par **systemd** (service système envisagé) avec démarrage automatique ; fonctionnement sans session utilisateur connectée.
- Compte de service à privilèges minimaux ; chemins, droits et accès aux données configurés pour ce contexte.
- L'activation du mode serveur **n'active pas** l'écoute sur les interfaces réseau ni l'exposition Internet.
- Passage poste ↔ serveur : configuration supervisée, vérification et, si nécessaire, migration des permissions/emplacements de données ; aucune conversion silencieuse susceptible de rendre les preuves inaccessibles.

### 3.3 Installation : parcours attendu

~~~text
Installation native OSIA
  |
  +--> Mode d'exécution ?
          |
          +--> Poste de travail
          |      -> moteur à la demande
          |      -> V1 : frontend web local recommandé
          |      -> client GTK natif : ultérieurement
          |
          +--> Serveur
                 -> service systemd permanent
                 -> frontend web ?
                       |
                       +--> Oui : navigateur autorisé
                       |
                       +--> Non : API seule
                                 (avertissement V1 ;
                                  client GTK distant futur)
~~~

L'activation de l'accès réseau, de l'authentification distante et du reverse proxy est un **parcours séparé** du choix poste/serveur et du choix frontend.

## 4. API et transport (T1.5)

- API REST pour consulter/commander et SSE pour la progression des tâches, découvertes, budgets, demandes d'approbation et états du moteur.
- Les événements métier importants sont conservés côté moteur : une reconnexion doit reconstruire l'état courant et rattraper, si possible, les événements manqués. SSE n'est **pas** l'unique source de vérité.
- Aucun appel facturable, collecte ou modification métier ne doit être déclenché par une simple requête GET/consultation d'état.
- Frontend web et API peuvent être servis sous une même origine (recommandé pour le navigateur) ; authentification, contrôle d'origine et anti-CSRF sont requis selon le modèle de session.
- HTTP/3/QUIC pourra transporter HTTP et SSE plus tard. WebTransport et WebSocket ne sont **pas** requis par T1.5 ; l'ajout d'un transport différent exigerait un besoin mesuré et un arbitrage complémentaire.
- API versionnée et contrats testés indépendamment des interfaces, afin de permettre le client GTK ultérieur.

## 5. Accès local, distant et sécurité (T1.7)

- Par défaut, l'API écoute **uniquement sur l'interface loopback** et le frontend local ne provoque aucune exposition réseau.
- L'accès distant est **opt-in** et administré séparément ; aucune ouverture automatique de port vers le LAN ou Internet.
- Les accès distants exigent une authentification adaptée, des autorisations, un transport chiffré et une protection contre les attaques courantes ; l'accès via VPN ou tunnel sécurisé demeure possible. Un reverse proxy HTTPS externe est une option privilégiée, **pas** une installation imposée.
- Pour les clients GTK distants futurs : mêmes politiques de droits/quotas que le frontend web, avec mécanisme d'authentification client dédié à définir. Ne jamais transférer les secrets de fournisseurs IA dans le client.
- Désactiver le frontend web supprime l'interface de consultation servie, **pas** l'API. La désactivation d'OSIA Core rend toutes les interfaces inopérantes.
- Les flux SSE ne doivent jamais exposer des informations à une session non autorisée ; revalidation des droits à la reconnexion et révocation des sessions nécessaires.
- Les connecteurs de collecte et les fournisseurs IA restent soumis aux politiques d'autorisation, de confidentialité et de budget des lots B et D.

## 6. Maintenance, notifications et migration (T1.6)

- **Mises à jour logicielles manuelles exclusivement** : aucune installation ni téléchargement de nouvelle version sans action explicite.
- Détection de nouvelle version et notification dans l'interface : vérification périodique configurable/désactivable, sans télémétrie ni donnée d'investigation. En mode API seule, consultation de la version et des notifications via un mécanisme administratif documenté.
- Installation via mécanismes natifs Linux ou hors ligne ; formats, dépôt de paquets et canal de publication restent à préciser.
- Lorsqu'une migration est nécessaire : contrôle de compatibilité, pause/sécurisation du moteur, sauvegarde **cohérente de la base et des pièces externes**, contrôle de migration et reprise. Une simple copie de la DB peut être insuffisante lorsqu'elle est ouverte.
- Revenir au binaire antérieur n'assure **pas** la compatibilité des données migrées : retour arrière ou restauration supervisée à partir d'un instantané cohérent et d'une version compatible.
- Après coupure/crash, ne pas rejouer automatiquement un appel externe potentiellement facturé lorsque son issue reste inconnue ; réconcilier avant reprise.
- Les données et preuves sont conservées au changement de version ou de mode ; les secrets ne sont pas inclus dans les sauvegardes/export standards sauf dispositif explicitement dédié et autorisé.

## 7. Conditions de recette du lot T1

1. Sur poste Linux, installation native sans Docker ; lancement à la demande, ouverture du web local et accès au moteur.
2. Sur serveur Linux, installation native et démarrage systemd sans session interactive.
3. Fermeture du navigateur pendant une investigation : le moteur poursuit et les résultats sont visibles après reconnexion.
4. Service arrêté pendant une opération : état persistant récupéré, coût potentiellement engagé non répété aveuglément.
5. Installation serveur sans frontend web : API utilisable, aucune page frontend servie, avertissement utilisateur V1 explicite.
6. Basculer l'option frontend web sans réinstaller le cœur et sans supprimer de dossier d'investigation.
7. Sans configuration réseau expresse, aucune écoute sur une interface publique/LAN.
8. Accès distant non authentifié ou non autorisé refusé ; accès chiffré exigé pour le distant.
9. Client REST et flux SSE reflètent un même état durable, y compris après reconnexion.
10. Une requête de lecture ou une reconnexion SSE n'entraîne pas de dépense IA ou de collecte.
11. Vérification de version : notification uniquement ; aucun téléchargement/installation automatique ; mode désactivé possible.
12. Migration interrompue : sauvegarde vérifiée, reprise ou restauration supervisée sans destruction silencieuse.
13. Reconfiguration poste ↔ serveur : chemins et permissions contrôlés ; données conservées.
14. Contrats API suffisamment indépendants pour un deuxième client non-React ; futur GTK non déclaré livré.

**Statut des tests :** critères de recette documentaires ; **aucun développement ni test d'exécution réalisé** à ce stade.

## 8. Points non arbitrés (ne pas déduire de T1)

- **OUVERT — packaging :** familles Linux et versions supportées, format de livraison (DEB candidat), exclusion physique des composants vs activation, signature et canaux de publication.
- **OUVERT — configuration :** détails de l'assistant, politiques systemd --user/service système, chemins XDG ou système, migrations de profils.
- **OUVERT — réseau/sécurité :** ports, identité/sessions, autorisation multi-utilisateur éventuelle, dispositif TLS et procédure d'accès distant.
- **OUVERT — mise à jour :** mécanisme concret de notification sans télémétrie et protocole de migration.
- **PROPOSÉ, non validé par T1 :** Python/FastAPI pour le moteur, SQLite pour les données, React/TypeScript pour la V1 web (ce dernier est le candidat de conception transversale).
- **REPORTÉ :** développement, distribution et ergonomie détaillée du client Rust/GTK 4/gtk-rs/libadwaita ; capacité multiserveurs du client, qui reste une suggestion et non une décision validée.

## 9. Traçabilité

- Décisions T1.1–T1.7 : échanges utilisateur de cadrage technique, 05–06/11/2026 ; option D spécifique utilisateur pour T1.2, T1.6 et T1.7.
- Cadrage A–D : quatre lots fonctionnels validés, textes intégraux à importer dans le dépôt.
- Conception parent : [TECHNIQUE.md](TECHNIQUE.md) — autres arbitrages T2–T8 toujours ouverts.
