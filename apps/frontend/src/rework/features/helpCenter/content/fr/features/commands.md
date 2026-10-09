---
title: Les commandes
order: 45
description: Lancer un prompt de l'équipe depuis le champ de saisie, en tapant /.
icon: bolt
---

# Les commandes

Une **commande** est un raccourci vers un prompt de l'équipe. Dans une
conversation, tapez `/` puis son nom et l'agent reçoit directement le texte du
prompt, sans passer par la bibliothèque.

C'est utile pour les demandes que vous refaites souvent : une relecture, un
résumé, une recherche cadrée.

## Donner une commande à un prompt

Sur la page **Prompts** de l'équipe, chaque prompt peut porter une commande —
un mot court, en minuscules, sans accent ni espace : `resume`, `relecture`,
`note-interne`. Le champ se trouve juste sous le titre du prompt.

> Attribuer une commande demande le rôle **Éditeur**, comme la création d'un
> prompt. Tout membre de l'équipe peut ensuite l'utiliser.

Une commande est propre à une équipe : deux équipes peuvent avoir chacune leur
`/resume`, mais à l'intérieur d'une équipe elle ne peut désigner qu'un seul
prompt. Un prompt sans commande reste utilisable normalement depuis la
bibliothèque.

Quand vous importez un prompt déjà porteur d'une commande déjà prise dans
l'équipe d'accueil, un suffixe est ajouté (`/resume-2`) pour que les deux
restent joignables.

## Lancer une commande

Dans le champ de saisie d'une conversation, **vide**, tapez `/` : la liste des
commandes de l'équipe s'ouvre au-dessus. Continuez à taper pour la filtrer.

Avec un **agent ReAct**, le menu propose aussi vos commandes de prompts
personnels, à côté des commandes de l'équipe et des skills plateforme. Un libellé
indique chaque origine. Si deux prompts ont la même commande, sélectionnez la
ligne voulue : la complétion conserve ce prompt précis. Une commande de prompt
saisie sans sélection utilise d'abord le prompt de l'équipe, puis votre prompt
personnel si l'équipe n'a pas de correspondance. Dans votre espace personnel,
vos commandes ne sont proposées qu'une fois. Les agents Deep conservent leur
fonctionnement actuel.

- **↓** et **↑** parcourent la liste ;
- **Tab** complète la commande sans l'envoyer ;
- **Entrée** l'envoie ;
- **Échap** referme la liste et garde ce que vous avez tapé.

Vous pouvez placer un prompt disponible et plusieurs skills plateforme
n’importe où dans un message de chat, dans les deux ordres. La complétion conserve le texte avant
et après chaque invocation. À l’envoi, le prompt est développé à sa place et tous
les skills sélectionnés sont demandés ensemble. ReAct propose aussi vos prompts
personnels dans les chats d’équipe et précharge chaque skill distinct une fois.
Deep utilise les lectures natives décidées par le modèle ; demander un skill ne
garantit pas à lui seul son chargement.

Par exemple, `Avant /resume après /verify-answer` conserve « Avant » devant le
prompt de résumé et « après /verify-answer » derrière.

## Ce que voit la conversation

Votre message s'affiche comme la commande lancée, pas comme le texte complet du
prompt : la conversation reste lisible. Un bouton sur ce message ouvre le texte
réellement envoyé, si vous voulez le vérifier.

Pour lire ou adapter un prompt avant de l'envoyer, passez plutôt par la
bibliothèque — voir [Les prompts](/help/fr/features/prompts) et
[Les conversations](/help/fr/features/chat).

## Les skills de la plateforme

Pour un agent dont le runtime propose des skills, tapez `/`, choisissez un
skill avec **↑/↓** puis **Tab** ou **Entrée**, et ajoutez une demande si vous le
souhaitez. Par exemple :

`/compte-rendu Résume ces notes : nous avons choisi l'option A ; Alex préparera la proposition.`

Tab, un clic ou Entrée complète le nom sans envoyer la demande. Une fois le skill sélectionné, appuyez à nouveau sur Entrée ou sur le bouton d’envoi. Vous pouvez envoyer `/compte-rendu` seul : l'agent utilise le contexte
pertinent ou demande les notes manquantes. `argument-hint` s'affiche quand un skill
indique des informations utiles, sans rendre leur saisie obligatoire à l'envoi.
Le skill reste à l’endroit où vous l’insérez dans le texte. Écrire son nom exact avec un slash, puis un espace (par exemple `/compte-rendu `), le sélectionne aussi ; un collage utilise le même format. Copier tout le message ou sélectionner seulement le nom du skill conserve `/nom-du-skill`. En cas de commande de prompt homonyme, choisissez explicitement le prompt dans le menu pour l’exécuter.
Le catalogue dépend de l'agent sélectionné. L'agent peut aussi choisir
les skills pertinents lors d'une demande ordinaire et en utiliser plusieurs avant
de répondre. Une étape compacte indique le nom et l'origine du chargement : vous,
l'agent ou un agent enfant. Elle reste visible après réouverture du chat.

Les instructions chargées restent dans le contexte de la conversation et
s'appliquent selon la demande. Elles n'ajoutent ni outils ni permissions.

`/skill` est réservé. Un ancien prompt portant cette commande reste disponible
dans la bibliothèque et modifiable ; renommez sa commande pour retrouver son
raccourci. Une nouvelle affectation, un import ou une promotion avec cette
commande sont refusés.
