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

- **↓** et **↑** parcourent la liste ;
- **Tab** complète la commande sans l'envoyer ;
- **Entrée** l'envoie ;
- **Échap** referme la liste et garde ce que vous avez tapé.

Le `/` n'ouvre la liste qu'en **début de message vide** : écrire `/` au milieu
d'une phrase reste du texte ordinaire.

Vous pouvez ajouter du texte après la commande : il est ajouté à la fin du
prompt. `/resume en dix lignes` envoie le prompt de résumé suivi de « en dix
lignes ».

## Ce que voit la conversation

Votre message s'affiche comme la commande lancée, pas comme le texte complet du
prompt : la conversation reste lisible. Un bouton sur ce message ouvre le texte
réellement envoyé, si vous voulez le vérifier.

Pour lire ou adapter un prompt avant de l'envoyer, passez plutôt par la
bibliothèque — voir [Les prompts](/help/fr/features/prompts) et
[Les conversations](/help/fr/features/chat).
