---
title: Rôles et droits
order: 65
description: Qui peut faire quoi — les rôles au sein d'une équipe et à l'échelle de la plateforme.
icon: gavel
---

# Rôles et droits

Vos droits dépendent de vos **rôles**. Il en existe deux niveaux, indépendants
l'un de l'autre :

- les **rôles d'équipe** — ce que vous pouvez faire **au sein d'une équipe** ;
- les **rôles de plateforme** — des responsabilités **transverses**, en dehors
  de toute équipe.

Tout utilisateur authentifié peut **utiliser la plateforme** : il n'y a pas de
rôle « global » qui conditionne l'accès de base. Les rôles ne font qu'ouvrir des
droits supplémentaires. Chaque droit est vérifié **côté serveur** à chaque
action (voir [Sécurité & autorisation](https://site.fredlab.dev)).

```mermaid
flowchart TB
  U["Utilisateur authentifié<br/>(peut utiliser la plateforme)"]

  subgraph platform["Rôles de plateforme — hors équipe"]
    PA["Admin plateforme"]
    PO["Observateur plateforme"]
  end

  subgraph team["Rôles d'équipe — dans une équipe (cumulables)"]
    TA["Admin"]
    TE["Éditeur"]
    TAN["Analyste"]
    TM["Membre (baseline)"]
  end

  U --> team
  U -.-> platform
```

## Les rôles d'équipe

Au sein d'une équipe, chaque membre porte un ou plusieurs rôles. Ils sont
**cumulables** : une même personne peut être à la fois Admin et Éditeur,
chaque rôle étant accordé séparément.

| Rôle         | Peut                                                                                                                                                                                         | Ne peut pas (sauf autre rôle)                                            |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Admin**    | Gérer les membres et leurs rôles ; définir la politique d'équipe (quotas, profils de modèles autorisés, serveurs MCP, limites de stockage/ingestion) ; consulter la configuration pour audit | Créer/modifier agents, prompts ou politique de routage                   |
| **Éditeur**  | Gérer les agents, les prompts partagés, la politique de routage et le corpus documentaire                                                                                                    | Modifier la politique d'équipe, créer des équipes ou attribuer des rôles |
| **Analyste** | Créer et lancer des campagnes d'évaluation, gérer les corpus d'évaluation                                                                                                                    | Gérer le corpus général, la gouvernance ou les membres                   |
| **Membre**   | Utiliser les agents et prompts de l'équipe, gérer ses prompts personnels, quitter l'équipe                                                                                                   | Modifier un réglage, une politique ou une ressource partagée             |

> **Admin et Éditeur sont orthogonaux, pas hiérarchiques.**
> L'Admin gouverne (membres, politique) mais n'a **aucun** droit sur les
> agents, prompts ou le routage tant qu'il n'est pas aussi Éditeur — et
> inversement. Cumuler les deux, c'est deux droits distincts, pas un super-rôle.

Le rôle **Membre** est la base implicite : automatique dès qu'on porte un rôle
au-dessus, ou attribué directement. Une équipe garde toujours **au moins un
Admin** — impossible de retirer le dernier.

## Les rôles de plateforme

En dehors des équipes, deux rôles portent des responsabilités transverses. Ils
**ne donnent aucun accès aux données** d'une équipe.

- **Admin plateforme** — gouverne le **registre des équipes** (lesquelles
  existent) : lister toutes les équipes, en supprimer une, ou « secourir » une
  équipe restée sans administrateur. C'est aussi lui qui amorce la première
  attribution du rôle Admin à la création d'une équipe.
- **Observateur plateforme** — accède à l'**observabilité transverse** : les KPI et
  analytics à l'échelle de la plateforme (Admin plateforme en hérite).

> **Un rôle de plateforme ne remplace jamais un rôle d'équipe.** Un
> Admin plateforme qui ne détient aucun rôle dans une équipe donnée y est
> **bloqué** pour toute écriture : il ne peut ni créer une bibliothèque, ni
> toucher aux agents de cette équipe. Toute action sur les données d'une équipe
> exige un rôle d'équipe explicite.

La gestion de l'**infrastructure** (Kubernetes, cloud) relève d'une équipe
d'exploitation distincte, en dehors du modèle de rôles applicatif.

## Comment c'est appliqué

- Chaque rôle est un **droit enregistré côté serveur**, indépendant de la
  façon dont vous vous connectez — se connecter prouve seulement qui vous
  êtes, cela n'accorde par soi-même aucun rôle.
- Chaque action est **vérifiée côté serveur**, pas seulement masquée dans
  l'interface : masquer un bouton ne suffit jamais à autoriser une action.
- Votre **espace personnel** n'est accessible qu'à vous : personne, pas même un
  Admin plateforme, ne peut y accéder.

Pour le détail du mécanisme d'autorisation, voir
[Sécurité & autorisation](https://site.fredlab.dev). Pour gérer les
membres et leurs rôles, voir [Administrer son équipe](/help/fr/features/teams).
