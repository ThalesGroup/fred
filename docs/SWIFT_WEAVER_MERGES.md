# Reprendre les changements Swift dans Weaver

Méthode pour les mainteneurs et assistants. L'état des portages et les SHA de la
tranche traitée sont dans le [dossier de suivi](../WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md).
Ce document décrit le travail d'intégration, pas l'architecture opérationnelle.
Les [instructions du dépôt](../AGENTS.md) restent applicables.

## Commencer par le comportement produit

Expliquer ce que le changement apporte à l'utilisateur avant son mécanisme.
Identifier le propriétaire Weaver de chaque donnée, droit et transition : un
fichier Swift ne désigne pas nécessairement le bon composant cible. Les extractions
pures et composants visuels peuvent être proches ; admission, catalogue de modèles,
publication documentaire, sessions et permissions demandent un examen des contrats.
Un diff sans conflit ne prouve ni qu'un écran est raccordé ni qu'un comportement
est conservé. L'absence de code à porter peut être une conclusion valable.

## Fixer deux inventaires

1. **Nouveaux commits Swift** depuis le dernier SHA réellement intégré. Actualiser
   les références par fetch, sans merge automatique ; enregistrer base Weaver,
   borne Swift intégrée et cible Swift examinée. Figer ces trois SHA pour le lot.
2. **Comportements précédemment différés**, avec source Swift, décision, portage
   Weaver et preuves. Leur commit peut déjà être dans l'ascendance : un autre
   merge ne réappliquera pas les comportements écartés.

Ne pas déplacer la borne Swift intégrée après un simple portage ou cherry-pick.
Ne pas la déduire de HEAD Weaver ou du nom d'une branche. Vérifier le merge et ses
parents dans Git. Les branches de backport sont des pistes : vérifier leur base
et leur contenu avant utilisation. Si l'histoire Swift a divergé, l'exposer avant
d'utiliser un intervalle de commits supposé linéaire.

## Préparer des lots autonomes

- Le maître d'oeuvre définit le périmètre, les dépendances et les critères de fin ;
  les assistants réalisent les missions explicitement attribuées. Ne pas lancer
  d'assistants ni de nouveaux chats uniquement parce que cette méthode existe.
- Pour chaque changement, classer : reprise directe, adaptation Weaver, déjà
  couvert, différé ou exclu avec motif. Toute exclusion porte sur un comportement
  précis ; ne pas abandonner une valeur produit parce que sa première implémentation
  utilise une couche supprimée.
- Réutiliser un checkout approprié. Une branche `codex/port-<lot>` est utile pour
  isoler le diff, mais ne sépare pas les fichiers d'un checkout partagé. Vérifier
  statut et activité avant un changement de branche. Un worktree est une option
  de coordination, pas une obligation ni une création automatique.
- Recenser les chemins partagés avant travail parallèle. Désigner le propriétaire
  des edits ; séquencer les changements de contrat et leur génération. Ne jamais
  stager les modifications d'un autre auteur pour simplifier l'intégration.
- Préférer de petits changements proches des propriétaires actuels. Eviter les
  renommages/reformatages sans nécessité, catalogues concurrents, doubles autorités
  et couches de compatibilité spéculatives.

## Réaliser et examiner l'intégration

1. Examiner l'apport Swift et les consommateurs actifs Weaver. Ne pas restaurer
   le Control Plane Python, OpenFGA, l'ancienne ingestion ou leurs migrations pour
   faire passer le diff. Replacer le besoin dans son propriétaire actuel.
2. Conserver les contrats d'autorisation, d'identité, de délégation et d'admission
   du dépôt. Vérifier les nouveaux raccords et les reprises, pas seulement les helpers.
3. Modifier les contrats à leur source puis régénérer les clients sur les sources
   réunies. Ne pas résoudre les conflits en éditant manuellement les types générés.
   Ajouter les migrations nécessaires sans réécrire une migration existante.
4. Lors d'un merge autorisé, examiner le résultat par rapport aux deux parents.
   Refuser les résolutions globales ours/theirs et les cherry-picks aveugles.
   Réexaminer toute résolution de conflit réutilisée. Ne pas réécrire l'histoire
   partagée ou forcer un push comme méthode d'intégration.
5. Appliquer la qualité du dépôt et les tests proportionnés explicitement prévus
   dans la mission. Rapporter les commandes réellement exécutées et les limites ;
   ne pas additionner des suites qui se recouvrent ni confondre mock et déploiement.
6. Mettre à jour le suivi avec décisions, commits de portage, génération des contrats,
   notes opérateur et réception restante. Une nouvelle arrivée Swift devient un
   delta explicite ; elle ne change pas silencieusement la base d'un lot en cours.

La mise en production, les politiques vivantes et migrations de données sont des
actions distinctes. Les commits, merges, pushes et déploiements nécessitent leur
autorisation ; la préparation d'un prompt ne les autorise pas.

## Reprise durable et nettoyage

Dans le rapport du lot, garder base/branche, sources Swift, décisions ouvertes,
chemins appartenant au lot, état du travail, preuves et prochaine action. Le rapport
seul ne sauvegarde pas du code : avant une interruption ou un nettoyage, préserver
le diff binaire et les nouveaux fichiers explicitement attribués, ou le commit
autorisé. Vérifier empreintes et restauration hors du checkout actif. Exclure
secrets, .env, caches, bases et fichiers privés des archives.

La coordination locale et les sauvegardes survivent à un redémarrage ; elles ne
remplacent pas une sauvegarde hors du disque. Les décisions nécessaires à l'équipe
doivent aussi figurer dans le suivi versionné, sans lien obligatoire vers un chat
ou un chemin personnel. Garder les rapports comme preuves historiques et archiver
les anciennes consignes au lieu de les laisser présenter un faux état courant.
Ne supprimer branches, worktrees ou backups qu'après vérification d'intégration,
de récupérabilité et d'absence de travail actif. Pas de git clean/reset automatique.

La stratégie et le suivi restent hors arc42. Après validation du parcours selon
le skill architecture, mettre à jour les chapitres existants et leurs annexes ;
jusque-là, conserver les propositions dans le rapport de travail.


## Décision PowerPoint — 5 novembre 2026

Le raccord durable décrit dans `WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md` remplace le
lancement asyncio à la sauvegarde et la réparation par polling Swift. CP accepte
et décide la disponibilité ; Temporal orchestre ; le worker du pod appelle sa
bibliothèque installée et confirme après persistance. Les modèles communs sont
scopés à l'organisation **et au pod logique**, sans activation transverse aux pods.

Décision explicite pour cette première version : ne pas enrichir le tour avec
un suivi des usages, des interruptions ou du décommissionnement. Les usages
simultanés à une suppression/remplacement et leur rétention feront l'objet d'un
lot transversal. Ne pas assimiler refus de nouveaux échanges et protection de
tous les tours déjà admis. Aucun chapitre arc42 ne décrit ce parcours comme reçu
en déploiement sur la seule base des tests locaux.
