---
title: Les agents
order: 20
description: Créer un agent depuis un template, le configurer, gérer son cycle de vie.
icon: smart_toy
---

# Les agents

Un **agent** est un assistant IA configuré pour un usage précis. La page
**Agents** de votre équipe liste les agents disponibles ; c'est aussi de là que
vous en créez de nouveaux.

## Template et instance

La création se fait à partir d'un **template** — un modèle d'agent fourni par
la plateforme. Vous obtenez une **instance** : votre agent concret, que vous
configurez librement et qui appartient à votre équipe. C'est toujours à une
instance que vous parlez dans le chat.

## Configurer un agent

À la création puis à tout moment, un agent se règle sur plusieurs points :

- **Le prompt d'engagement** : les instructions permanentes qui définissent son
  rôle, son ton et ses limites.
- **Les prompts attachés** : des prompts de votre bibliothèque qui complètent
  son cadrage.
- **Les ressources** : les documents ou bibliothèques que l'agent peut
  exploiter pour répondre.
- **Les capacités** : les fonctions supplémentaires qu'il peut mobiliser (voir
  [Les capacités](/help/fr/features/capabilities)).

![TODO: capture — formulaire de configuration d'un agent](assets/agents-form.png)

## Cycle de vie

- **Dupliquer** : repartez d'un agent existant pour en créer une variante sans
  tout reconfigurer.
- **Suspendre** : un agent peut être suspendu — notamment lorsqu'une capacité
  dont il dépend est désactivée pour l'équipe. Un agent suspendu reste visible
  mais n'est plus utilisable tant que sa dépendance n'est pas rétablie.
- **Supprimer** : retirez définitivement un agent dont vous n'avez plus besoin.

> Créer et modifier des agents requiert le rôle **Éditeur** ou
> **Administrateur** (voir [les rôles](/help/fr/getting-started/join-create-team)).
