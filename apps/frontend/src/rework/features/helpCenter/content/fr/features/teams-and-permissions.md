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
| **Éditeur**  | Créer et modifier agents, prompts, ressources et routage des modèles                | Gérer les membres ou les réglages de l'équipe          |
| **Admin**    | Gérer les membres et leurs rôles, les réglages et la politique de l'équipe          | **Créer ou modifier un agent, un prompt, un document** |
| **Analyste** | Créer et lancer des campagnes d'évaluation, gérer les corpus d'évaluation           | Toucher au corpus général, aux membres, aux réglages   |

> **Admin et Éditeur sont deux autorisations distinctes, et non deux échelons.**
> Ce point est fréquemment mal compris : un Admin gouverne l'équipe et n'a aucun
> droit sur ses agents ni ses documents tant qu'il n'est pas également Éditeur.
> Porter les deux rôles revient à détenir deux autorisations, non à occuper un
> niveau supérieur.

**Membre** est la base : automatique dès qu'on porte un rôle au-dessus. Et une
équipe garde toujours **au moins un Admin** — retirer le dernier est refusé.

## Entrer dans une équipe

La **marketplace** liste les équipes visibles de votre organisation. Une équipe
**publique** y figure et se rejoint d'un clic si elle est ouverte ; sinon un
Admin de l'équipe doit vous ajouter. Une équipe **privée** n'apparaît pas du
tout, et ne se rejoint jamais seul : demandez à un de ses membres.

À noter : une équipe privée **ne peut pas** être ouverte à l'adhésion libre.
On y entre uniquement sur ajout par l'un de ses membres.

## Qui crée les équipes

La création d'une équipe est une action d'administration : elle demande le rôle
de plateforme **Admin plateforme** ou **Gestionnaire d'équipes**. Ces rôles sont
accordés et ne font pas partie des droits d'un utilisateur ordinaire. Si vous
avez besoin d'une équipe, adressez-vous à votre administrateur.

Une précision importante : **celui qui crée une équipe n'en devient pas
administrateur.** Les administrateurs initiaux sont désignés explicitement au
moment de la création. Cette séparation est délibérée : créer une équipe relève
de l'administration de la plateforme, animer une équipe relève de l'équipe.

## Les réglages de l'équipe

La page **Réglages** rassemble ce qui gouverne l'équipe. L'accès à chaque
section dépend de votre rôle.

- **Membres** — ajouter, retirer, changer les rôles (**Admin**).
- **Paramètres** — la description de l'équipe, sa visibilité sur la marketplace,
  son mode d'adhésion, et le délai de **rétention** après lequel les
  conversations supprimées sont définitivement effacées (**Admin**).
- **Routage des modèles** — quel profil de modèle les agents de l'équipe
  utilisent, par défaut et selon l'opération. Laissé vide, le profil du
  déploiement s'applique (**Éditeur**).
- **Évaluations** — les campagnes de mesure de la qualité d'un agent
  (**Analyste** ou **Admin**). Voir le guide
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
