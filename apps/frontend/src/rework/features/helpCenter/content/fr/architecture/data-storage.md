---
title: Les magasins de données
order: 30
description: PostgreSQL, OpenSearch, object storage, Temporal, OpenFGA, Keycloak — rôle de chacun.
icon: database
---

# Les magasins de données

Chaque magasin est spécialisé pour un type d'information. Aucun composant
applicatif ne mélange ces responsabilités.

| Magasin                 | Rôle                                                            |
| ----------------------- | --------------------------------------------------------------- |
| **`PostgreSQL`**        | État, sessions, historique de conversation, checkpoints d'agent |
| **`OpenSearch`**        | Vector index pour le retrieval RAG                              |
| **Object storage (S3)** | Documents d'origine et objets produits                          |
| **`Temporal`**          | Orchestration durable des workflows (ingestion, tâches de fond) |
| **`OpenFGA`**           | Moteur d'autorisation ReBAC (tuples de relations)               |
| **`Keycloak`**          | Fournisseur d'identité OIDC, émission des JWT                   |

## PostgreSQL

Le magasin d'état relationnel : teams, agent instances, prompts, sessions et
**historique**. Il porte aussi les **checkpoints** qui permettent au
`fred-runtime` de restaurer l'état du graphe d'un agent entre deux tours (clé de
continuité : la `session_id`).

## OpenSearch

Le **vector index** interrogé par le `knowledge-flow` pour le retrieval RAG :
c'est la représentation vectorielle des documents qui permet à un agent de
retrouver les passages pertinents et de s'appuyer dessus.

## Object storage (S3-compatible)

Le magasin d'objets pour les **documents d'origine** (déposés ou produits par les
agents). L'implémentation est S3-compatible : `MinIO` en configuration type,
`SeaweedFS` en local, ou un stockage cloud (`GCS`) selon le déploiement.

## Temporal

L'orchestrateur de **workflows durables**. Il porte l'ingestion documentaire et
les tâches de cycle de vie, exécutées en arrière-plan sans bloquer le chemin de
conversation — c'est le pilier du **découplage** (voir
[Vue d'ensemble](/help/fr/architecture/index)).

## OpenFGA & Keycloak

- **`OpenFGA`** — le moteur **ReBAC** : il stocke les tuples de relations et
  répond aux checks d'autorisation (`CAN_USE_TEAM_AGENTS`…) exécutés côté pod.
- **`Keycloak`** — le fournisseur d'identité **OIDC** : authentification des
  utilisateurs et émission des **JWT** présentés à chaque appel.

Le détail du rôle de ces deux composants dans l'autorisation est en
[Sécurité & autorisation](/help/fr/architecture/security).

> La séparation entre object storage, vector index et métadonnées explique
> l'opération d'**audit du corpus**, qui vérifie leur cohérence (voir
> [Console d'administration](/help/fr/features/admin)).
