---
title: Les data stores
order: 30
description: PostgreSQL, OpenSearch, object storage, Temporal, OpenFGA, Keycloak — rôle de chacun.
icon: database
---

# Les data stores

Chaque data store est spécialisé pour un type d'information. Aucun composant
applicatif ne mélange ces responsabilités.

| Data store              | Rôle                                                              |
| ----------------------- | ----------------------------------------------------------------- |
| **`PostgreSQL`**        | State, sessions, conversation history, agent checkpoints          |
| **`OpenSearch`**        | Vector index pour le retrieval RAG                                |
| **Object storage (S3)** | Documents d'origine et objets produits                            |
| **`Temporal`**          | Durable orchestration des workflows (ingestion, background tasks) |
| **`OpenFGA`**           | ReBAC authorization engine (relationship tuples)                  |
| **`Keycloak`**          | Fournisseur d'identité OIDC, émission des JWT                     |

## PostgreSQL

Le state store relationnel : teams, agent instances, prompts, sessions et
**historique**. Il porte aussi les **checkpoints** qui permettent au
`fred-runtime` de restaurer l'état du graphe d'un agent entre deux tours (clé de
continuité : la `session_id`).

## OpenSearch

Le **vector index** interrogé par le `knowledge-flow` pour le retrieval RAG :
c'est la représentation vectorielle des documents qui permet à un agent de
retrouver les passages pertinents et de s'appuyer dessus.

## Object storage (S3-compatible)

Le object store pour les **documents d'origine** (déposés ou produits par les
agents). L'implémentation est S3-compatible : `MinIO` en configuration type,
`SeaweedFS` en local, ou un stockage cloud (`GCS`) selon le déploiement.

## Temporal

L'orchestrateur de **durable workflows**. Il porte l'document ingestion et
les lifecycle tasks, exécutées en arrière-plan sans bloquer le conversation path — c'est le pilier du **découplage** (voir
[Vue d'ensemble](/help/fr/architecture/index)).

## OpenFGA & Keycloak

- **`OpenFGA`** — le **ReBAC** engine : il stocke les relationship tuples et
  répond aux checks d'autorisation (`CAN_USE_TEAM_AGENTS`…) exécutés côté pod.
- **`Keycloak`** — l'identity provider **OIDC** : authentification des
  utilisateurs et émission des **JWT** présentés à chaque appel.

Le détail du rôle de ces deux composants dans l'autorisation est en
[Sécurité & autorisation](/help/fr/architecture/security).

> La séparation entre object storage, vector index et métadonnées explique
> l'opération d'**audit du corpus**, qui vérifie leur cohérence (voir
> [Console d'administration](/help/fr/features/admin)).
