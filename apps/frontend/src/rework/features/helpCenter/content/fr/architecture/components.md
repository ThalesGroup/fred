---
title: Les composants
order: 10
description: Rôle et responsabilités de chaque service et bibliothèque de la plateforme.
icon: widgets
---

# Les composants

La plateforme est un ensemble de services déployables indépendamment
(`apps/`) et de bibliothèques partagées (`libs/`).

## frontend

`apps/frontend` — SPA React. Catalogue d'agents, UI de conversation, gestion des
sessions. Il consomme les API `control-plane` et `knowledge-flow`, et ouvre le
execution stream (SSE) directement sur les pods agents.

## control-plane-backend

`apps/control-plane-backend` — le service de gestion centralisé. Il porte :

- les **teams**, **agent instances**, **sessions**, **prompts** et métadonnées ;
- la **découverte et l'enrôlement** des pods agents ;
- la résolution de l'exécution via `prepare-execution` : il détermine **quel pod
  sert quelle agent instance** et renvoie une URL ingress-relative + le contexte
  de session — **sans émettre de capacité** (voir
  [Sécurité](/help/fr/architecture/security)) ;
- l'application de la **governance** (policies de modèle, tools/MCP, prompts,
  data scope).

Il embarque également un worker `Temporal` pour ses background tasks.

> **Découverte des pods (état actuel).** Les pods sont enregistrés via une liste
> statique `runtime_catalog_sources` dans le `control-plane-backend`.

## knowledge-flow-backend

`apps/knowledge-flow-backend` — les long-running data operations :

- **document ingestion**, déclinée en trois profils de traitement
  (`fast`, `medium`, `rich`) ;
- **vector retrieval** pour le RAG (index dans `OpenSearch`) ;
- exécution durable sur **workflows `Temporal`** (jobs d'ingestion, lifecycle tasks).

## Agentic pods

Les pods agents exécutent la logique des agents. Ils sont tous traités à
l'identique par le `control-plane` et par le routage ingress.

- **`fred-agents`** (`apps/fred-agents`) — le pod fourni (_bundled_) :
  capacités `general`, `rag`, `sql`, `sentinel`, test harness, compatibilité
  OpenAI. Construit sur `fred-runtime` + `fred-sdk`.
- **`custom-agent-pod`** — un pod fourni par une équipe : n'importe quelle
  logique d'agent, n'importe quels outils, n'importe quel model provider.
  L'équipe importe `fred-runtime` + `fred-sdk`, déploie un standard container,
  et l'enregistre dans `runtime_catalog_sources`.

Chaque pod **authentifie et autorise lui-même** chaque requête (voir
[Sécurité](/help/fr/architecture/security)).

## Bibliothèques partagées

- **`fred-runtime`** (`libs/fred-runtime`) — l'execution engine : agent loop (ReAct / Deep) sur `LangGraph`, client `MCP`, HITL (human-in-the-loop),
  application `agent_app` du pod.
- **`fred-sdk`** (`libs/fred-sdk`) — les contrats d'exécution et la
  compatibilité OpenAI. C'est la surface qu'un `custom-agent-pod` importe pour
  se conformer au managed path.
- **`fred-core`** (`libs/fred-core`) — le socle commun partagé.
- **Capacités** — `libs/fred-capability-writable-document`,
  `libs/fred-capability-ppt-filler` : des capacités packagées, greffées aux
  agents.

## Le modèle d'extensibilité des pods

Une équipe construit son pod en important `fred-runtime` + `fred-sdk`. Une fois
le pod déployé et son `base_url` + `runtime_id` ajoutés à
`runtime_catalog_sources`, le `control-plane` l'enrôle et l'ingress gagne une
route `/runtime/{runtime_id}/`. Les agents vivent donc **hors du monorepo**, ce
qui découple leur lifecycle de celui de la plateforme.
