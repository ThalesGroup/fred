---
title: Les agents
order: 10
description: Créer un agent depuis un modèle, l'instruire, lui donner des fonctions.
icon: smart_toy
---

# Les agents

Un **agent** est un assistant IA configuré pour un usage précis. La page
**Agents** de votre équipe les rassemble.

> Créer ou modifier un agent demande le rôle **Éditeur**. Le rôle **Admin**
> seul ne le permet pas : les deux rôles sont indépendants, pas les échelons
> d'une même échelle (voir
> [Équipes et droits](/help/fr/features/teams-and-permissions)).

## D'un modèle à votre agent

Vous partez d'un **modèle** fourni par la plateforme — par exemple un modèle
capable de chercher dans des documents. Vous obtenez votre propre agent, qui
appartient à votre équipe et que vous réglez librement. C'est toujours à un
agent de votre équipe que vous parlez.

## Les quatre réglages

- **Les instructions** — les consignes de fond : son rôle, son ton, ses limites.
  C'est le réglage déterminant ; les autres le complètent.
- **Les prompts attachés** — des prompts de la bibliothèque qui complètent ces
  instructions (voir [Les prompts](/help/fr/features/prompts)).
- **Les ressources** — les bibliothèques de documents que l'agent peut
  consulter. Sans rattachement, il ne voit aucun document.
- **Les fonctions** — ce qu'il sait faire au-delà de répondre.

## Ce qu'un agent sait faire en plus de répondre

L'onglet **Capacités** décide de ce que l'agent a le droit de faire : chercher
dans les documents de l'équipe, exploiter une pièce jointe, rédiger un document
Word, remplir une présentation PowerPoint, produire une page web, prendre le
temps de raisonner par étapes…

Deux façons de choisir, via l'interrupteur **Avancé** en haut de l'onglet :

- **Simple** (par défaut, et recommandé) — vous cochez des **packs** : des
  ensembles qui vont naturellement ensemble. Une bascule active tout ce qu'il
  faut.
- **Avancé** — vous activez chaque fonction une par une, avec ses options.

Le mode Simple couvre les usages courants. Le mode Avancé reste accessible à
tout moment.

> **La liste des packs disponibles est celle qu'affiche l'interface**, pas
> celle-ci : elle évolue avec la plateforme, et chaque déploiement n'ouvre pas
> les mêmes. Dépliez un pack (**Capacités incluses**) pour voir son détail.

### Les trois états d'une fonction

À côté du nom de chaque pack, une rangée de pastilles donne l'état d'ensemble :

- **Activée** (pastille pleine) — active sur cet agent.
- **Disponible, non activée** (cercle vide) — votre équipe y a droit, mais elle
  n'est pas active ici. Vous pouvez l'activer.
- **Non autorisée** (pastille rouge) — la plateforme ne l'a pas ouverte à votre
  équipe. Le pack fonctionne quand même avec le reste ; demandez son ouverture
  si vous en avez besoin (voir
  [Administration](/help/fr/features/administration)).

## Dupliquer, suspendre, supprimer

- **Dupliquer** — repartir d'un agent existant pour en faire une variante. La
  configuration est copiée, mais **pas les fichiers** qu'elle référence : un
  modèle PowerPoint, par exemple, est à redéposer sur la copie.
- **Suspendu** — un agent suspendu reste visible mais inutilisable. C'est
  qu'une fonction dont il dépend a été désactivée, que l'accès de l'équipe y a
  été retiré, ou que sa configuration n'est plus valide. Voir
  [Problèmes courants](/help/fr/troubleshooting/common-problems).
- **Supprimer** — la suppression est définitive.
