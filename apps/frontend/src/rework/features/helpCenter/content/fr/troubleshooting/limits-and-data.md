---
title: Limites et données
order: 20
description: Quotas, temps de traitement, qui voit vos contenus, ce que devient une conversation supprimée.
icon: shield
---

# Limites et données

## Quotas et volumes

Chaque équipe dispose d'un **espace de stockage** pour ses documents. À
l'approche de la limite, un dépôt peut être refusé : allégez le corpus, ou
demandez un ajustement à un Admin de l'équipe. La consommation est affichée sur
la page Ressources.

Il n'y a **pas de plafond strict par fichier** : l'indication affichée dans la
fenêtre de dépôt est informative. Ce qui est appliqué, c'est le quota global de
l'équipe — un gros fichier y pèse simplement plus lourd. Ce quota ne concerne
pas les pièces jointes de conversation.

## Pourquoi c'est parfois long

- **La préparation d'un document** dépend de sa taille.
- **Une question très ouverte**, ou portant sur un gros volume, peut atteindre
  les limites de traitement. Ciblez davantage.
- Une lenteur générale et persistante, alors que votre demande est raisonnable,
  relève probablement d'un incident côté plateforme.

## Qui voit vos contenus

Vos contenus appartiennent à une **équipe** et ne sont visibles que par ses
membres. Votre **espace personnel** n'est visible que de vous — pas même d'un
Admin plateforme. Un rôle de plateforme ne donne accès à aucune donnée
d'équipe : il faut un rôle _dans_ l'équipe.

## Ce que devient une conversation supprimée

Elle est **masquée immédiatement**, puis effacée définitivement au terme du
délai de **rétention** fixé par l'équipe. Sans délai défini, l'effacement est
immédiat.

## Vos documents et le modèle de langage

Pour produire une réponse, les **extraits pertinents** de vos documents sont
envoyés au modèle de langage configuré pour votre équipe — lequel peut être
fourni par un prestataire externe. Le fournisseur dépend du routage des modèles
de votre déploiement, et c'est votre administrateur de plateforme qui connaît
les modalités applicables chez vous.

L'accès aux documents eux-mêmes, en revanche, reste dans le périmètre de
l'équipe : cela détermine qui, parmi vos collègues, peut les consulter.

## Quelle confiance accorder aux réponses ?

Les réponses d'un agent ne doivent pas être reprises sans vérification. Un agent
s'appuie sur un modèle de langage : il peut se tromper, et formuler une erreur
avec assurance. Les sources citées existent pour cela — **ouvrez-les** pour
toute réponse qui compte. Un agent qui ne cite aucune source n'a consulté aucun
document.

## Données personnelles et conformité

La page dédiée de votre déploiement est accessible à l'adresse `/gdpr`. Les
modalités exactes dépendent de la configuration : en cas de doute, adressez-vous
à votre administrateur de plateforme.
