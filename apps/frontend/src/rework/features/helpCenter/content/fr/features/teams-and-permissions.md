---
title: Équipes et droits
order: 50
description: Qui peut faire quoi dans une équipe, comment on y entre, et qui crée les équipes.
icon: groups
---

# Équipes et droits

Tout contenu appartient à une équipe et n'est visible que par ses membres. Vos
droits dépendent de votre **rôle** dans cette équipe.

## Les quatre rôles d'équipe

Ils sont **cumulables** : une même personne peut porter plusieurs rôles,
accordés séparément.

| Rôle         | Peut                                                                                | Ne peut pas, sans autre rôle                           |
| ------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **Membre**   | Utiliser les agents, lire les conversations et les fichiers de l'équipe, la quitter | Modifier quoi que ce soit de partagé                   |
| **Éditeur**  | Créer et modifier agents, prompts et ressources                                     | Gérer les membres ou les réglages de l'équipe          |
| **Admin**    | Gérer les membres et leurs rôles, les réglages et la politique de l'équipe          | **Créer ou modifier un agent, un prompt, un document** |
| **Analyste** | Créer et lancer des campagnes d'évaluation, gérer les corpus d'évaluation           | Toucher au corpus général, aux membres, aux réglages   |

> **Admin et Éditeur sont deux autorisations distinctes, et non deux échelons.**
> Ce point est fréquemment mal compris : un Admin gouverne l'équipe et n'a aucun
> droit sur ses agents ni ses documents tant qu'il n'est pas également Éditeur.
> Porter les deux rôles revient à détenir deux autorisations, non à occuper un
> niveau supérieur.

**Membre** est la base : automatique dès qu'on porte un rôle au-dessus. Et une
équipe garde toujours **au moins un Admin** — retirer le dernier est refusé.

## Publier des agents

Tout **Éditeur** peut partager les agents de l'équipe avec toute l'organisation
grâce à la marketplace des agents. Un **Admin** de l'équipe peut retirer un
agent de la marketplace sans être Éditeur. Le fonctionnement de la publication
est expliqué sur la page
[Les agents](/help/fr/features/agents#la-marketplace-des-agents).

La publication est **activée pour chaque équipe par l'administrateur de la
plateforme**, qui fixe aussi le nombre d'agents qu'une équipe peut publier. Si
l'administrateur la désactive plus tard, les agents publiés de l'équipe quittent
la marketplace.

## Entrer dans une équipe

La **marketplace** liste les équipes visibles de votre organisation. Une équipe
**publique** y figure avec sa façon d'y entrer :

- **Ouverte** : **Rejoindre** vous en rend membre d'un clic.
- **Sur demande** : **Demander à rejoindre** envoie une demande aux Admins de
  l'équipe.
- **Sur invitation** : un Admin de l'équipe doit vous ajouter ou vous envoyer
  un lien d'invitation.

Une équipe **privée** n'apparaît pas du tout, et ne se rejoint jamais seul :
demandez à un de ses membres.

À noter : une équipe privée **ne peut pas** être ouverte à l'adhésion libre ni
aux demandes. On y entre quand l'un de ses Admins vous ajoute ou vous envoie un
lien d'invitation.

Les pages d'une équipe ne s'ouvrent qu'à ses membres : un lien vers une équipe
dont vous n'êtes pas (ou plus) membre affiche **Vous n'êtes pas membre de cette
équipe**, avec **Demander à rejoindre** si l'équipe accepte les demandes.

### Demander à rejoindre une équipe

Sur la carte d'une équipe **Sur demande**, **Demander à rejoindre** ouvre un
court formulaire. Vous pouvez ajouter un message pour les Admins de l'équipe
(280 caractères au plus, eux seuls le lisent), puis **Envoyer la demande**. La
carte affiche alors **Demande envoyée** : **Annuler la demande** la retire tant
que personne n'a répondu.

La cloche vous donne la réponse. Si un Admin accepte, vous devenez **Membre**
et l'équipe passe dans **Vos équipes**. S'il refuse, la carte affiche
**Demande refusée** et le moment où vous pourrez la renouveler : 24 heures plus
tard. Une demande restée sans réponse est abandonnée au bout de 30 jours.

### Traiter les demandes (Admins)

Pour recevoir des demandes, un Admin de l'équipe choisit **Sur demande** dans
**Réglages → Paramètres → Mode d'adhésion**. Seule une équipe publique le
propose.

Chaque demande arrive dans les notifications des Admins de l'équipe, avec le
message de la personne : **Refuser**, à gauche, la décline ; **Accepter**, à
droite, en fait un **Membre**. La première réponse compte ; les autres Admins voient ensuite qui a
répondu. Les mêmes demandes figurent en haut de **Réglages → Membres**, sous
**Demandes en attente**, avec les mêmes boutons. Une demande refusée depuis
moins de 7 jours y reste affichée avec **Accepter quand même**, en cas
d'erreur.

Quitter **Sur demande** (ou rendre l'équipe privée) refuse toutes les demandes
en attente, et chaque personne en est prévenue.

### Liens d'invitation

Un Admin de l'équipe peut ouvrir **Réglages → Membres → Lien d'invitation** et
activer **Activer l'invitation par lien**. L'équipe dispose alors d'un lien,
affiché en entier avec un bouton **Copier**, à partager comme il le souhaite
(messagerie, e-mail…). Ouvrir ce lien puis choisir **Rejoindre l'équipe** vous
rend **Membre** ; un Admin peut ensuite vous donner d'autres rôles.

Le lien ne fonctionne que pour les personnes qui ont déjà accès à la
plateforme. Il ne donne pas accès à la plateforme elle-même : sans cet accès, le
lien mène à la page qui explique comment le demander.

Désactiver l'interrupteur met le lien en pause : il ne fonctionne plus jusqu'à
sa réactivation, avec le même lien. **Générer un nouveau lien** le remplace
définitivement : l'ancien lien ne fonctionne plus. Dans les deux cas, les
personnes déjà entrées restent membres.

## Qui crée les équipes

La création d'une équipe est une action d'administration : elle demande le rôle
de plateforme **Admin plateforme** ou **Gestionnaire d'équipes**. Ces rôles sont
accordés et ne font pas partie des droits d'un utilisateur ordinaire. Si vous
avez besoin d'une équipe, adressez-vous à votre administrateur.

Une précision importante : **celui qui crée une équipe n'en devient pas
administrateur.** Les administrateurs initiaux sont désignés explicitement au
moment de la création. Cette séparation est délibérée : créer une équipe relève
de l'administration de la plateforme, animer une équipe relève de l'équipe.

## La description de l'équipe

Chaque équipe a une **description** : quelques phrases qui disent ce que
l'équipe veut accomplir avec l'IA. Elle est obligatoire à la création de
l'équipe (20 à 500 caractères) et s'affiche sur la carte de l'équipe dans la
marketplace, pour que chacun comprenne à quoi sert l'équipe.

Un **Admin** de l'équipe peut la réécrire à tout moment dans les **Réglages**
de l'équipe, mais ne peut pas la laisser vide.

Une équipe créée avant que la description devienne obligatoire affiche
« Description à compléter par l'administrateur de l'équipe. » tant qu'aucune
n'a été rédigée. Ses Admins voient un rappel sur la page d'accueil de l'équipe
et dans ses réglages ; le rappel disparaît dès que la description est
enregistrée.

## Les réglages de l'équipe

La page **Réglages** rassemble ce qui gouverne l'équipe. L'accès à chaque
section dépend de votre rôle.

- **Membres** — ajouter, retirer, changer les rôles, partager des liens
  d'invitation, répondre aux demandes (**Admin**).
- **Paramètres** — la description de l'équipe, sa visibilité sur la marketplace,
  son mode d'adhésion, et le délai de **rétention** après lequel les
  conversations supprimées sont définitivement effacées (**Admin**).
- **Modèles** — parmi les modèles de langage que la plateforme ouvre à
  l'équipe : ceux que les membres peuvent utiliser, celui par défaut, et si le
  raisonnement démarre activé pour chacun (**Admin** ; les Éditeurs et
  Analystes le consultent). Le modèle par défaut ne peut pas être désactivé.
  Désactiver un modèle affiche d'abord les agents qui le conseillaient : ils
  suivent alors le modèle par défaut de l'équipe. Les conversations qui
  l'utilisaient reviennent au modèle conseillé de l'agent. Un modèle
  nouvellement ouvert par la plateforme arrive activé.

## L’application d’évaluation

Ouvrez l’evaluator enregistré depuis l’entrée **Apps** de l’équipe. C’est une
application autonome, pas une section des réglages de l’équipe. Elle doit être
déployée, enregistrée et activée pour votre équipe ; ses droits d’accès restent
applicables. Si elle est indisponible, contactez votre administrateur. Voir
[Évaluer un agent](/help/fr/guides/evaluate-agents).

## Les rôles de plateforme

Cinq rôles existent en dehors des équipes. Ils portent des responsabilités
transverses et **ne donnent aucun accès aux données d'une équipe** :

| Rôle                                | Responsabilité                                                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Admin plateforme**                | Tout ce qui suit, plus la suppression d'une équipe, la gestion des utilisateurs et le secours d'une équipe restée sans Admin |
| **Gestionnaire d'équipes**          | Créer des équipes et voir la liste de toutes les équipes                                                                     |
| **Gestionnaire de fonctionnalités** | Ouvrir ou fermer les fonctions disponibles pour chaque équipe                                                                |
| **Éditeur de prompt plateforme**    | Modifier les instructions communes ajoutées à tous les agents                                                                |
| **Observateur plateforme**          | Consulter les indicateurs d'usage à l'échelle de la plateforme                                                               |

> **Un rôle de plateforme ne remplace jamais un rôle d'équipe.** Un Admin
> plateforme sans rôle dans votre équipe ne peut ni y toucher aux agents, ni y
> lire les conversations. Et personne, pas même lui, n'accède à votre espace
> personnel.

## Comment c'est appliqué

Chaque droit est un enregistrement côté serveur, vérifié **à chaque action** —
pas seulement masqué dans l'interface. Se connecter prouve qui vous êtes ; cela
n'accorde par soi-même aucun rôle.

Il vous manque un droit ? Voir
[Problèmes courants](/help/fr/troubleshooting/common-problems).
