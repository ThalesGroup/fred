---
title: Les prompts
order: 40
description: Créer, organiser et réutiliser les textes de vos espaces.
icon: chat
---

# Les prompts

Un **prompt** est un texte réutilisable : une question type, une consigne ou un
cadre de réponse. La page **Prompts** présente la bibliothèque de l'espace
ouvert : **organisation, équipe, projet ou espace personnel**. Chaque prompt
appartient à cet espace.

Si vous appartenez à plusieurs organisations, choisissez l'organisation dans
l'accueil avant d'ouvrir sa bibliothèque de prompts ou votre espace personnel.

Les droits de l'espace déterminent ce que vous pouvez faire. Un accès en
lecture permet de consulter, copier et mettre en favori. Le rôle **Éditeur**
de cet espace permet aussi de créer, modifier, dupliquer et supprimer les
prompts, ainsi que de gérer leurs catégories. Un rôle d'Admin technique seul
ne donne aucun accès à leur contenu.

## Créer, consulter, réutiliser

Dans la bibliothèque, choisissez la création d'un prompt et renseignez :

- **Le titre**, destiné à la lecture, que vous pourrez modifier.
- **Le nom logique (commande)**, obligatoire et unique dans cet espace. Il contient
  de 1 à 64 lettres minuscules non accentuées, chiffres, tirets ou caractères
  `_`, sans espace ni `/`. Par exemple, `resume` donne la commande `/resume`.
  Ce nom ne peut plus être modifié après création ; `skill` est réservé.
- **Le contenu**, le texte complet à réutiliser. Il ne peut pas être vide.
- Si besoin, une **description**, une **catégorie** et des **tags**.

Cliquez sur une carte pour consulter le texte complet et le copier. Le menu
de la carte propose les actions de gestion selon vos droits. Modifier le
titre ne change ni l'identité du prompt ni sa commande. Les champs que vous
ne modifiez pas restent inchangés.

**Dupliquer** crée un prompt indépendant dans le même espace. Choisissez un
nouveau nom de commande disponible ; le titre, le contenu, la description,
la catégorie et les tags sont repris. Aucun suffixe de commande n'est ajouté
automatiquement. Les modifications de la copie ne changent pas l'original.

## Catégories et tags

Les **catégories** appartiennent à l'espace. Vous pouvez les créer et les
renommer, puis classer un prompt dans une catégorie ou le laisser **Sans
catégorie**. Pour supprimer une catégorie utilisée, reclassez d'abord ses
prompts ou retirez leur catégorie. Il n'y a pas de réordonnancement manuel,
ni de catégories ou prompts d'exemple créés automatiquement.

Les **tags** sont des étiquettes facultatives : jusqu'à 20 par prompt, de
64 caractères au plus chacune. La recherche de la bibliothèque porte sur le
titre, le nom de commande, la description et les tags. Elle se combine avec
le filtre de catégorie et les favoris. Les nombres des catégories comptent
leurs prompts ; ce ne sont pas des compteurs d'utilisation.

## Favoris

Cliquez sur l'**étoile** pour ajouter ou retirer un favori. Ce choix est propre
à votre compte et ne modifie ni le contenu ni les droits du prompt. Le filtre
**Favoris** existe dans la bibliothèque et dans le panneau des prompts d'une
conversation.

Le retrait de vos droits ne supprime pas vos favoris, mais ils ne permettent
pas de continuer à lire un prompt devenu inaccessible. Supprimer le prompt
supprime les favoris qui lui étaient associés.

## Où les utiliser

Les sélecteurs ne proposent pas tous la même bibliothèque :

| Parcours                                                  | Prompts proposés et effet                                                                                                                                                        |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Page **Prompts**                                          | Bibliothèque de l'espace ouvert, parmi les quatre types d'espaces, selon vos droits.                                                                                             |
| Recherche de l'accueil                                    | Prompts lisibles de vos espaces ; un résultat ouvre sa fiche dans son espace d'origine.                                                                                          |
| Panneau des prompts et menu `/` d'une conversation        | Espace de la conversation et, s'il est disponible, votre espace personnel de la même organisation. Dans une conversation personnelle, cette bibliothèque n'apparaît qu'une fois. |
| Champ d'instructions d'un agent proposant la bibliothèque | Prompts de l'espace de cet agent uniquement.                                                                                                                                     |

Dans une **conversation**, choisir un prompt dans le panneau insère son texte
dans le brouillon : vous pouvez l'adapter avant d'envoyer, sans modifier le
prompt enregistré. Une **commande** `/nom` est résolue avec le texte courant
au moment de l'envoi. Voir [Les conversations](/help/fr/features/chat) et
[Les commandes](/help/fr/features/commands).

Dans la **configuration d'un agent**, choisir un prompt remplit le champ avec
une copie de son texte, que vous enregistrez avec l'agent. Ce n'est pas une
référence vivante : modifier ou supprimer ensuite le prompt de la bibliothèque
ne met pas à jour ces instructions. Voir [Les agents](/help/fr/features/agents).

Le marketplace est un parcours distinct. Ses publications ne sont pas ajoutées
aux sélecteurs de conversation ou d'instructions décrits ici.

## Propriété et départ d'un auteur

L'auteur indique la provenance du prompt ; il n'a pas de permission spéciale.
Dans un espace collectif, les éditeurs peuvent modifier et supprimer les
prompts même après le départ de leur créateur. Retirer des droits ne supprime
pas les prompts et ne les transfère pas à une autre personne.

L'espace personnel reste privé. Un départ n'ouvre aucun nouveau droit sur sa
bibliothèque, aucune reprise exceptionnelle et aucun transfert automatique.
La publication explicite d'un prompt ne donne pas accès au reste de cet espace.
