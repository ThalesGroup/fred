---
title: Vue d'ensemble
order: 0
description: Architecture logique de la plateforme, composants et flux d'exécution d'une requête.
icon: architecture
---

# Architecture technique

Cette section décrit l'**architecture logique** de la plateforme : les
composants, leurs responsabilités, la façon dont ils communiquent, et le modèle
de sécurité qui les relie.

> **Public visé.** Contrairement au reste de ce centre d'aide, cette section
> s'adresse à des profils techniques — ingénieurs IT, architectes, data
> scientists, développeurs. Le vocabulaire y est précis et les composants sont
> désignés par leur nom d'origine (`control-plane`, `knowledge-flow`,
> `fred-agents`, `OpenFGA`, `Keycloak`…).

## Vue logique

La plateforme se décompose en quatre plans, du poste client jusqu'aux magasins
de données :

```mermaid
flowchart TB
  FE["frontend (React SPA)"]

  subgraph plane["Plan applicatif"]
    CP["control-plane-backend"]
    KF["knowledge-flow-backend"]
  end

  subgraph runtime["Agent runtime layer"]
    FA["fred-agents (bundled pod)"]
    CA["custom-agent-pod (team-provided)"]
  end

  subgraph infra["Magasins de données"]
    PG["PostgreSQL"]
    OS["OpenSearch"]
    OBJ["Object storage (S3)"]
    TMP["Temporal"]
    FGA["OpenFGA"]
    KC["Keycloak"]
  end

  LLM["LLM APIs (externe)"]

  FE --> CP
  FE --> KF
  FE -->|"SSE, JWT"| FA
  FE -->|"SSE, JWT"| CA
  CP --> PG
  CP --> FGA
  KF --> OS
  KF --> OBJ
  KF --> TMP
  FA --> LLM
  CA --> LLM
  FA --> PG
```

- Le **frontend** parle au `control-plane` et au `knowledge-flow` pour tout ce
  qui est catalogue, sessions et documents ; il ouvre en revanche le flux
  d'exécution **directement** sur le pod agent (jamais relayé par le
  `control-plane`).
- Le détail de chaque composant est en
  [Les composants](/help/fr/architecture/components).

## Le flux d'une requête

L'exécution d'un tour d'agent suit le **managed path** (le seul autorisé pour le
frontend en production). Trois participants : le navigateur, le
`control-plane-backend`, et un pod `fred-runtime`.

```mermaid
sequenceDiagram
  participant B as Browser
  participant CP as control-plane
  participant Pod as agent pod (fred-runtime)
  B->>CP: POST prepare-execution (Bearer JWT)
  Note over CP: valide l'appartenance à la team,<br/>résout le binding runtime + le contexte
  CP-->>B: ExecutionPreparation (execute_stream_url, team_id, contexte)
  Note over CP,B: URL ingress-relative — aucun grant, aucune expiration
  B->>Pod: POST execute_stream_url (Bearer JWT, runtime_context.team_id)
  Note over Pod: valide le JWT Keycloak,<br/>autorise per-request (ReBAC OpenFGA)
  Pod-->>B: SSE stream (status, deltas, tool calls, final)
```

Point clé : le `control-plane` résout **où** l'agent s'exécute (via
`prepare-execution`) mais **n'émet aucune capacité** et ne relaie jamais le flux
SSE. Le navigateur appelle le pod directement avec le **JWT Keycloak de
l'utilisateur** ; le pod authentifie ce token et **autorise lui-même** chaque
requête. Le détail du modèle est en
[Sécurité & autorisation](/help/fr/architecture/security).

## Pourquoi cette forme

Trois principes structurent ce découpage :

- **Découplage.** Le chemin de conversation reste réactif pendant que
  l'ingestion, l'évaluation et les traitements de fond s'exécutent durablement
  via `Temporal`.
- **Governance policy-first.** Les décisions (modèle, tool/MCP, prompt, agent,
  périmètre de données) sont résolues à partir de **policies**, pas codées en
  dur.
- **Extensibilité.** Les agents sont construits et déployés dans leurs propres
  dépôts ; le `control-plane` les découvre et route vers eux, sans dépendance au
  monorepo. Un `custom-agent-pod` est, du point de vue de l'utilisateur,
  indiscernable des pods fournis.
