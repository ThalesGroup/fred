---
title: Administration
order: 60
description: Ce qui dépasse une seule équipe, et pourquoi vous n'y avez sans doute pas accès.
icon: admin_panel_settings
---

# Administration

Certaines décisions dépassent le cadre d'une équipe : quelles équipes existent,
quelles fonctions leur sont ouvertes, qui détient un rôle de plateforme. Elles
vivent dans la **console d'administration**.

> Les pages dépendent de votre rôle : les Responsables d'organisation gèrent
> les fonctionnalités métier, les administrateurs techniques leur périmètre
> administratif (voir [Équipes et droits](/help/fr/features/teams-and-permissions)).

## Y accéder

**Menu profil** (en bas du panneau de navigation) → **Administration**. Chacun
arrive sur la première page qu'il a le droit de voir ; deux administrateurs
n'accèdent donc pas nécessairement à la même page.

## Applications de l'organisation

En tant que **Responsable d'organisation**, ouvrez **Administration > Fonctionnalités > Apps**.
Enregistrez l'adresse de l'interface et, si nécessaire, celle de l'API fournies
par l'opérateur du service. Le service doit déjà être déployé et de confiance.
Un nouvel enregistrement n'est pas autorisé : utilisez **Modifier** pour le
vérifier et autoriser son usage dans l'organisation. Les paramètres des équipes
et projets peuvent restreindre cet accès. L'enregistrement ne déploie pas le
service et ne nécessite aucun redémarrage de Fred.

La roue dentée près du nom de l'organisation gère les ressources de cet espace ;
**Administration** contient la configuration des fonctionnalités de l'organisation.

## Bases de connaissances de l'organisation

Chaque déploiement d'application ou de collecteur KB sert une seule organisation.
Réutiliser l'image ne partage ni le service, ni les identifiants, ni les données.

Dans **Administration > Fonctionnalités > Bases de connaissances**, le ou la
Responsable enregistre l'identité du collecteur et les noms des références de
connexion fournis par l'opérateur. L'opérateur déploie le collecteur ; actualisez
la page pour voir et autoriser ses définitions. Aucun redémarrage de Fred n'est requis.

Le ou la Responsable d'espace ouvre ensuite **Bases de connaissances** dans son
espace pour créer une collecte : paramètres de source, références de connexion,
traitement des documents et intervalle de synchronisation. La source est fixée à
la création ; l'intervalle et la suspension restent modifiables. Les documents
s'ouvrent dans l'explorateur habituel en lecture seule. Supprimer la collecte retire
aussi ses documents. Ne saisissez jamais de valeurs secrètes dans Fred.

## Ce qu'on y trouve

- **Équipes** — la liste de toutes les équipes, et leur création.
- **Rôles plateforme** — qui détient quel rôle transverse.
- **Utilisateurs** — les comptes de la plateforme.
- **Fonctionnalités** — le catalogue des fonctions et leur ouverture par équipe.
- **Prompts plateforme** — les instructions communes aux agents.
- Pour choisir le modèle qui rédige les propositions de l'**assistant de création**,
  ouvrez **Fonctionnalités → Modèles → Modèles par défaut → Conception d'agents**.
  Sans choix dédié, l'assistant suit le modèle par défaut de l'espace.
- **Interface utilisateur** — le thème proposé par défaut et les thèmes
  disponibles pour les utilisateurs.
- **Annonces** — les bandeaux et les patch notes affichés aux utilisateurs.
- **Marketplaces** — qui peut publier des agents dans la marketplace, et
  combien.
- **Analytiques** — les indicateurs d'usage à l'échelle de la plateforme.
- **Activité** — les traitements en cours et leur historique.
- **Auto-test** et **Audit du corpus** — les vérifications de bon
  fonctionnement.
- **Données plateforme** — export et import de l'état de la plateforme.

## Le thème de l'interface

Chaque utilisateur choisit son thème (Galet, Cobalt, Nuage…) et son mode clair,
sombre ou système dans **Profil** → **Interface : thème et mode**.

Sur la page **Interface utilisateur**, chaque thème a sa tuile, avec ses trois
couleurs principales. Un **Admin plateforme** y décide :

- des **thèmes proposés** : un thème désactivé disparaît du profil des
  utilisateurs ;
- du **thème par défaut**, avec **Définir par défaut** : celui des
  utilisateurs qui n'ont encore rien choisi. Galet l'est tant que rien n'a été
  changé. Le thème par défaut reste toujours proposé.

Chaque changement est enregistré aussitôt.

Un utilisateur dont le thème n'est plus proposé passe au thème par défaut. Son choix est conservé : il le retrouve si le thème est de nouveau proposé. Choisir
un thème dans son profil, même celui déjà affiché, le garde ensuite si le thème
par défaut change. Si un seul thème est proposé, le
profil n'affiche plus que le mode. Les changements s'appliquent aussitôt pour
l'administrateur, et pour les autres utilisateurs à leur retour sur
l'application ou dans la minute.

Pour ajouter un thème aux couleurs de votre organisation, voir
[Créer un thème personnalisé](/help/fr/guides/custom-theme).

## Marketplaces

Sur la page **Marketplaces**, un **Admin plateforme** décide dans quelles
équipes les éditeurs peuvent publier des agents dans la marketplace (voir
[Les agents](/help/fr/features/agents#la-marketplace-des-agents)) :

- une ligne **Activation de la publication** : **Désactivé** ou **Activé**,
  et combien d'agents une équipe peut publier (5 sauf changement). Toutes les
  équipes la suivent, y compris celles créées plus tard ;
- pour chaque équipe, **Désactivée**, **Défaut** ou **Activée**. Son
  **Nombre d'agents max** suit la valeur par défaut ; **Personnaliser** lui en
  donne un propre, avec un retour possible au défaut.

Désactiver la publication pour une équipe retire ses agents publiés de la
marketplace ; la confirmation annonce d'abord combien. Baisser le nombre
d'agents max garde les agents déjà publiés mais bloque les nouvelles
publications.

## Le template de présentation de la plateforme

Sur la page **Fonctionnalités**, la ligne **Générer une présentation** a une
icône **Réglages de la plateforme**. Un **Admin plateforme** y choisit le template PowerPoint des agents
qui n'en ont pas à eux (le template intégré tant que rien n'est changé) :

- **Téléverser un template .pptx** — le fichier est lu en arrière-plan. Tant
  que la lecture n'a pas réussi, ou si elle échoue, les agents gardent le
  template précédent.
- **Utiliser un modèle de vision** — indisponible dans Weaver. L'analyse de structure fonctionne sans appel de modèle ; vérifiez les noms et types à la main.
- **Vérifier les slides** — renommez une slide, changez son type ou
  mettez-la de côté. Les corrections s'enregistrent à la fermeture et valent
  pour tous les agents qui utilisent ce template. Une nouvelle lecture du même
  fichier les garde ; un autre fichier repart sans corrections. Sans template
  téléversé, vous corrigez de la même façon les slides du template intégré.
- **Réinitialisation au template intégré** — supprime le template et toutes les
  corrections, celles du template intégré comprises, après confirmation.

Un changement atteint tous les agents en moins d'une minute.

## Qui ouvre les fonctions à votre équipe

Le ou la **Responsable d'organisation** autorise les fonctionnalités métier
sur la page **Fonctionnalités**. Les Responsables d'équipe et de projet peuvent
restreindre ce périmètre, mais ne peuvent pas ouvrir une fonctionnalité non
autorisée par l'organisation. Adressez cette demande à votre Responsable
d'organisation.

Lorsqu'une fonction déjà utilisée par un agent est refermée, cet agent est
**suspendu** jusqu'à son rétablissement.

## Deux pages d'usage, à ne pas confondre

- **L'usage de votre équipe** — la page **Usage** de l'équipe : la consommation
  dans le temps, par agent et par modèle, plus votre part personnelle. La vue
  d'ensemble de l'équipe demande un rôle **Admin**, **Éditeur** ou
  **Analyste** ; un simple Membre ne voit que sa propre consommation.
- **L'usage de la plateforme** — la page **Analytiques** de la console, à
  l'échelle de tous les utilisateurs. Elle demande le rôle **Observateur
  plateforme**.

Les deux pages ne font donc pas double emploi : leurs périmètres et leurs
conditions d'accès diffèrent.
