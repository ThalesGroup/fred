---
title: Les commandes
order: 45
description: Lancer un prompt depuis le champ de saisie, en tapant /.
icon: bolt
---

# Les commandes

Une **commande** est un raccourci vers un prompt, le vôtre ou celui d'une
équipe. Dans une conversation, tapez `/` puis son nom : à l'envoi, l'agent
reçoit directement le texte du prompt, sans passer par la bibliothèque.

C'est utile pour les demandes que vous refaites souvent : une relecture, un
résumé, une recherche cadrée.

## Donner une commande à un prompt

Sur la page **Prompts**, chaque prompt peut porter une commande : un mot court,
en minuscules, sans accent ni espace : `resume`, `relecture`, `note-interne`.
Le champ se trouve juste sous le titre du prompt.

> Dans votre espace personnel, vous pouvez donner une commande à n'importe
> lequel de vos prompts : elle vous suit dans toutes vos conversations. Dans
> une équipe, il faut le rôle **Éditeur**, comme pour créer un prompt ; tout
> membre de l'équipe peut ensuite l'utiliser.

Une commande est propre à un espace : deux équipes peuvent avoir chacune leur
`/resume`, et vous le vôtre, mais dans une même équipe ou dans votre espace
personnel elle ne peut désigner qu'un seul prompt. Un prompt sans commande
reste utilisable normalement depuis la bibliothèque.

Quand vous importez un prompt dont la commande est déjà prise dans l'espace
d'accueil, un suffixe est ajouté (`/resume-2`) pour que les deux restent
joignables.

## Lancer une commande

Dans le champ de saisie d'une conversation, tapez `/` : la liste des commandes
s'ouvre au-dessus. Vous pouvez le faire n'importe où dans votre message, même
quand le champ contient déjà du texte : commencez la commande après un espace
ou sur une nouvelle ligne.

Continuez à taper pour chercher. La liste garde les commandes dont le nom
contient ce que vous tapez, en majuscules comme en minuscules, et place en
premier celles dont le nom commence ainsi.

La liste est rangée en trois parties, chacune sous son titre :

1. **Équipe « nom de l'équipe »** : les commandes de l'équipe de la
   conversation ;
2. **Espace personnel** : vos propres commandes, proposées quel que soit
   l'agent ;
3. **Skills plateforme** : les skills que l'agent sait utiliser.

Une partie qui n'a rien à proposer n'apparaît pas. Dans votre espace
personnel, vos commandes ne sont listées qu'une fois, sous **Espace
personnel**.

Si l'équipe et vous avez une commande du même nom, elle apparaît dans les deux
parties : choisissez la ligne voulue, c'est ce prompt précis qui sera lancé. Si
vous tapez le nom sans choisir de ligne, la commande de l'équipe passe en
premier, puis la vôtre si l'équipe n'en a pas.

- **↓** et **↑** parcourent la liste ;
- **Entrée**, **Tab** ou un clic ajoutent la commande à votre message, sans
  rien envoyer ;
- une fois la commande ajoutée, **Entrée** envoie le message ;
- **Échap** referme la liste et garde ce que vous avez tapé.

Il faut donc appuyer deux fois sur Entrée pour lancer une commande choisie dans
la liste : la première fois l'ajoute, la seconde envoie. Entre les deux, vous
pouvez compléter votre message.

La commande ajoutée s'affiche comme une petite étiquette dans votre message.
Cliquez dessus pour relire le texte du prompt avant d'envoyer.

Vous pouvez placer plusieurs commandes de prompt et plusieurs skills
plateforme n'importe où dans un message, dans l'ordre que vous voulez ; la
liste continue de proposer vos commandes après la première. Le texte écrit
avant, entre et après est conservé. À l'envoi, le texte de chaque prompt prend
la place de sa propre commande et tous les skills choisis sont demandés
ensemble. Chaque commande a sa propre étiquette, et vous pouvez utiliser la
même commande plusieurs fois.

Par exemple, `D'abord /resume puis /ton merci /verify-answer` envoie
"D'abord", le prompt de résumé, "puis", le prompt de ton et
"merci /verify-answer", dans cet ordre.

Un message peut contenir jusqu'à 16 commandes de prompt. Si l'une d'elles
n'est plus utilisable, par exemple parce que son prompt a été supprimé, rien
n'est envoyé : un message vous indique quelle commande retirer ou choisir à
nouveau, et ce que vous avez écrit reste dans le champ.

## Ce que voit la conversation

Votre message s'affiche tel que vous l'avez tapé, avec une étiquette pour
chaque commande à la place du texte complet des prompts : la conversation
reste lisible. Cliquez sur une étiquette pour ouvrir le texte réellement
envoyé pour cette commande, si vous voulez le vérifier. Copier le message
redonne la ligne que vous avez tapée.

Pour adapter un prompt avant de l'envoyer, passez plutôt par la bibliothèque :
voir [Les prompts](/help/fr/features/prompts) et
[Les conversations](/help/fr/features/chat).

## Les skills de la plateforme

Certains agents disposent de skills : des marches à suivre toutes prêtes,
fournies par la plateforme. Quand l'agent en propose, ils apparaissent dans la
liste sous **Skills plateforme**. Tapez `/`, choisissez un skill avec **↑/↓**
puis **Entrée**, **Tab** ou un clic, et ajoutez une demande si vous le
souhaitez. Par exemple :

`/meeting-minutes Résume ces notes : nous avons choisi l'option A ; Alex préparera la proposition.`

Comme pour une commande, choisir un skill l'ajoute à votre message sans rien
envoyer : appuyez à nouveau sur Entrée ou sur le bouton d'envoi. Vous pouvez
envoyer `/meeting-minutes` seul : l'agent utilise ce que contient déjà la
conversation ou vous demande les notes manquantes. Certains skills affichent
après leur nom une indication de ce qu'il est utile de leur fournir ; elle
n'est jamais obligatoire.

Le skill reste à l'endroit où vous l'insérez dans le texte. Écrire son nom
exact avec un slash, puis un espace (par exemple `/meeting-minutes `), le
sélectionne aussi ; un collage utilise le même format. Copier tout le message
ou sélectionner seulement le nom du skill conserve `/nom-du-skill`. Si un
prompt porte le même nom qu'un skill, choisissez la ligne voulue dans la
liste : leur icône les distingue.

Les skills proposés dépendent de l'agent choisi. Selon l'agent, les
instructions d'un skill demandé sont lues avant de répondre, ou seulement s'il
le juge utile. L'agent peut aussi décider de lui-même d'utiliser un ou
plusieurs skills pour une demande ordinaire. Une ligne dans le détail de sa
réponse indique alors le nom du skill et qui l'a demandé : vous, l'agent ou un
agent auquel il a confié une partie du travail. Elle reste visible quand vous
rouvrez la conversation.

Les instructions d'un skill restent valables pour la suite de la conversation
et s'appliquent quand la demande s'y prête. Elles ne donnent à l'agent ni outil
ni droit supplémentaire.

`/skill` est réservé. Un ancien prompt portant cette commande reste disponible
dans la bibliothèque et modifiable ; renommez sa commande pour retrouver son
raccourci. Une nouvelle affectation, un import ou une promotion avec cette
commande sont refusés.
