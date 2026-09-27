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

> Dépliez un pack (**Capacités incluses**) pour voir son détail. Ce que fait
> chaque capacité, ses limites et un exemple d'emploi figurent sur la page
> [Les capacités](/help/fr/features/capabilities). **La liste affichée par
> l'interface fait foi** : elle évolue avec la plateforme, et chaque
> déploiement n'ouvre pas les mêmes capacités.

### N'activez que ce dont l'agent a besoin

Activer tous les packs « au cas où » est un réflexe courant, et c'est le
réglage qui produit les agents les moins fiables.

**L'agent choisit seul parmi ce que vous lui donnez.** À chaque message, il
décide quelle fonction employer. Plus la liste est longue, plus il risque de
prendre la mauvaise route, et plus la réponse est lente. Un agent qui dispose
des trois fonctions utiles à sa mission est plus prévisible qu'un agent qui en
a douze.

**Certaines fonctions coûtent cher.** L'extraction exhaustive, par exemple, lit
le document entier : elle est lente et demande une confirmation avant chaque
usage. Sur un agent qui n'en a pas besoin, elle ne sert qu'à être déclenchée
par erreur.

**Les fonctions modifient l'interface de conversation.** Les pièces jointes
ajoutent un bouton, la production de documents ouvre un panneau latéral,
l'accès aux ressources peut afficher un sélecteur de bibliothèque. Un agent
sur-équipé présente à ses utilisateurs des commandes qui ne servent pas à son
usage.

S'y ajoute une question de robustesse : un agent est **suspendu** dès qu'une
des fonctions dont il dépend est retirée à l'équipe. Moins il en dépend, moins
il y est exposé.

La méthode qui fonctionne part de l'usage : formulez en une phrase ce que
l'agent doit savoir faire, activez le strict nécessaire, puis complétez si un
manque apparaît à l'usage. Il est toujours plus simple d'ajouter une capacité
que de diagnostiquer un agent qui en a trop.

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
