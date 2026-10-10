---
title: Les conversations
order: 20
description: Reprendre un échange, joindre un fichier, insérer un prompt, récupérer un document.
icon: forum
---

# Les conversations

Chaque échange avec un agent est une **conversation**. Elle conserve les
messages, les pièces jointes et les documents produits.

Comment poser une question et lire une réponse est traité dans
[Première conversation](/help/fr/getting-started/first-conversation) ; cette
page couvre le reste.

## Gérer ses conversations

La liste de gauche garde vos conversations. Un interrupteur **Grouper par
agent** bascule l'affichage (désactivé par défaut). Vous pouvez en **reprendre**
une, en **démarrer** une nouvelle, ou en **supprimer** une.

Une conversation supprimée est **masquée immédiatement**, puis effacée
définitivement au terme du délai de rétention fixé par l'équipe. Sans délai
défini, l'effacement est immédiat.

## Joindre un fichier

Vous pouvez joindre un fichier à un message : l'agent en tient compte **le
temps de la conversation**, et n'y accède pas depuis une autre. Pour un document
durable et partagé, passez par les [ressources](/help/fr/features/resources) de
l'équipe.

Joindre un fichier suppose que l'agent dispose du pack **Pièces jointes** ;
sinon le trombone n'apparaît pas.

## Choisir les sources de la réponse

**Documents uniquement** demande à l'agent de répondre à partir des documents,
sans compléter les informations manquantes par ses connaissances générales.
Ce mode inclut les pièces jointes de la conversation et les documents de l'équipe
lorsque les deux sources sont activées. Si l'agent n'autorise qu'une source, seule
celle-ci est recherchée. Si les documents ne contiennent pas la réponse, l'agent
reçoit la consigne de le signaler.

**Connaissances générales + documents** combine les sources documentaires
activées et les connaissances générales. **Connaissances générales** ne lance
pas de recherche documentaire.

## Choisir le modèle et le raisonnement

Le bouton à droite du champ de saisie indique le modèle de langage qui répond.
Une conversation démarre sur le modèle conseillé par l'agent. Ouvrez le bouton
pour choisir un autre modèle parmi ceux activés pour l'équipe : ce choix vaut
pour cette conversation seulement, et une nouvelle conversation repart du
modèle conseillé.

Quand le modèle sait raisonner, le même menu propose **Faible** ou **Élevé
(Raisonnement)**. Il démarre sur le réglage choisi par l'équipe pour ce modèle.
Le raisonnement donne des réponses plus réfléchies, mais plus lentes et plus
coûteuses.

Si le modèle choisi n'est plus disponible, un message le signale et la
conversation revient au modèle conseillé.

## Insérer un prompt

Plutôt que de retaper une demande récurrente, insérez le contenu d'un prompt
enregistré dans le champ de saisie, puis modifiez-le avant d'envoyer. C'est un
raccourci pour ce message, pas un réglage durable de la conversation.

Un prompt porteur d'une commande se lance plus court encore : tapez `/` dans un
champ vide — voir [Les commandes](/help/fr/features/commands).

## Récupérer un document produit

Certains agents produisent un fichier — un document rédigé, une présentation,
une page web. Il apparaît dans la conversation, d'où vous le téléchargez. Un
document rédigé en conversation s'obtient au format Word ou Markdown.

En cas de difficulté, voir
[Problèmes courants](/help/fr/troubleshooting/common-problems).
