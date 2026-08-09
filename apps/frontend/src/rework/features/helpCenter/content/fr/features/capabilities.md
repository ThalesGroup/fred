---
title: Les capacités des agents
order: 50
description: Ce qu'un agent sait faire en plus de discuter, choisi simplement par « packs ».
icon: extension
---

# Les capacités des agents

Une **capacité**, c'est quelque chose que votre agent sait faire en plus de
discuter avec vous : chercher une information dans les ressources de votre
équipe, résumer un document, rédiger un fichier Word, remplir une présentation
PowerPoint… Lors de la création (ou de la modification) d'un agent, l'onglet
**Capacités** vous laisse choisir ce que cet agent aura le droit de faire.

## Deux façons de choisir : Simple et Avancé

En haut de l'onglet, un interrupteur **« Avancé »** bascule entre deux
affichages :

- **Simple** (par défaut, recommandé) : vous choisissez des **packs** —
  des ensembles de capacités qui vont naturellement ensemble. Une seule
  bascule active tout ce qu'il faut, sans vous poser de questions techniques.
- **Avancé** : vous activez et réglez chaque capacité une par une, avec ses
  options détaillées.

> **Notre conseil.** Si vous n'êtes pas à l'aise avec l'idée des « outils » que
> l'agent utilise en autonomie, **restez en mode Simple**. Il couvre les besoins
> courants et vous évite des réglages fins qui ne servent qu'à des usages
> pointus. Vous pourrez toujours modifier votre choix plus tard.

## Les packs de capacités (mode Simple)

Les packs sont regroupés en **sections** selon ce qu'ils apportent :

- **Données et connaissances**
  - **Accès aux ressources de l'équipe** : l'agent peut chercher et exploiter
    les documents partagés de votre équipe pour répondre. Voir le guide
    [Créer un assistant sur vos ressources](/help/fr/guides/build-rag-assistant).
  - **Pièces jointes à une conversation** : l'agent peut exploiter les fichiers
    que vous déposez dans une conversation — sans accéder au reste des
    ressources de l'équipe.
- **Production de documents**
  - **Générer un document Word** : l'agent rédige un document texte que vous
    pouvez télécharger. Voir le guide
    [Produire des documents](/help/fr/guides/generate-documents).
  - **Remplir un document PowerPoint** : à partir d'un modèle `.pptx`, l'agent
    remplit une présentation finalisée.
- **Intelligence et orchestration**
  - **Raisonnement** : l'agent prend le temps de réfléchir par étapes avant de
    répondre, pour les questions plus complexes.
- **Actions et intégration** : encore vide pour le moment — d'autres capacités
  viendront s'y ajouter.

Activer un pack enclenche automatiquement toutes les capacités qu'il contient
et qui sont **disponibles pour votre équipe** (voir juste en dessous). Vous
n'avez pas à activer chaque élément à la main.

## Savoir en un coup d'œil : les trois états

Chaque pack peut être **déplié** (« Capacités incluses ») pour voir le détail
des capacités qu'il regroupe. À côté du titre, une **rangée de petites pastilles**
vous donne déjà l'état d'ensemble sans même déplier. Chaque capacité peut être
dans l'un de **trois états** :

- 🟢 **Activée** (pastille verte pleine) : la capacité est bien active sur cet
  agent. Tout va bien.
- ⚪ **Disponible, mais non activée** (cercle gris vide) : votre équipe y a
  droit, mais elle n'est pas active sur cet agent — par exemple parce que
  personne ne l'a activée, ou qu'elle a été retirée dans le mode Avancé. Vous
  pouvez l'activer si vous en avez besoin.
- 🔴 **Non autorisée par l'administrateur** (pastille rouge) : l'administrateur
  de la plateforme n'a pas ouvert cette capacité pour votre équipe. Elle ne
  peut donc pas être utilisée, même si le pack est activé.

Quand un pack contient au moins une capacité dans ce dernier état, la mention
**« Capacités manquantes »** apparaît en rouge sur la ligne du pack. Ce n'est
pas bloquant : le pack fonctionne avec les capacités disponibles, et la ou les
capacités manquantes sont simplement ignorées. Si vous en avez besoin,
demandez à votre administrateur de l'activer pour l'équipe.

## Le rôle de l'administrateur

C'est l'**administrateur de la plateforme** qui décide quelles capacités sont
ouvertes à votre équipe, depuis la
[Console d'administration](/help/fr/features/admin). C'est pourquoi certaines
capacités peuvent apparaître en rouge (non autorisées) : ce n'est pas une
erreur de votre part.

Enfin, si une capacité déjà utilisée par un agent est **désactivée** par
l'administrateur, cet agent est **suspendu** jusqu'à son rétablissement (voir
[Les agents](/help/fr/features/agents)).
