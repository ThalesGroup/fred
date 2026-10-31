# 1. System overview

The following views describe Fred's core platform, which supports both its
ready-to-use workspace and SDK extensions, through document ingestion, agent
access, governance and model use.

## 1.1. Six components and their responsibilities

The frontend provides the workspace for documents, conversations and
administration. It calls Control Plane API for resource management and Agent Pods
directly for chat. An Agent Pod is a runtime that hosts agents and their
capabilities. Fred supplies `fred-agent` as its default Agent Pod.

Control Plane API governs spaces, access and document operations; its worker
handles lifecycle cleanup, including space deletion. Knowledge Flow worker
extracts and indexes document content, while Knowledge Flow API serves that
knowledge to agent capabilities through internal endpoints.

**Legend:** 🟦 Fred · 🟨 COTS · 🟪 Extensions · ⬜ Concepts

```mermaid
flowchart TB
    ui["Frontend<br/>Documents, chat and administration"]
    subgraph cp["Control Plane"]
        api["Control Plane API<br/>Governance and document drive"]
        worker["Control Plane worker<br/>Background lifecycle operations"]
    end
    pod["Agent Pod<br/>Assistant and capability execution<br/>Default: fred-agent"]
    subgraph kf["Knowledge Flow"]
        kfa["Knowledge Flow API<br/>Internal knowledge access"]
        kfw["Knowledge Flow worker<br/>Extraction, embeddings and indexing"]
    end
    ui -->|"Documents / administration"| api
    ui <-->|"Chat / streamed answers"| pod
    pod -->|"Resolve authorized context"| api
    pod -->|"Capabilities"| kfa
    api -.->|"Processing via Temporal"| kfw

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class ui,api,worker,pod,kfa,kfw fred
    class cp,kf neutral
```

These are six logical responsibilities. Control Plane API and its worker
currently share a process. The dotted arrow represents asynchronous processing
coordinated through Temporal, the workflow engine.

## 1.2. Ingestion: the path from a document to knowledge

A document enters Fred through Control Plane API, within a space where the user
may contribute. Control Plane stores the original and starts processing through
Temporal. Knowledge Flow worker extracts content, computes embeddings (numerical
representations used for semantic search) and writes the processing results.

```mermaid
flowchart TB
    ui["Frontend"]
    api["Control Plane API<br/>Admission and publication"]
    temporal["Temporal<br/>Durable processing"]
    kfw["Knowledge Flow worker<br/>Extract, embed and index"]
    artifacts[("Object storage / vector index<br/>Originals and processing results")]
    facts[("PostgreSQL<br/>Placement and publication")]
    ui -->|"Upload into a space"| api
    api -->|"Store original"| artifacts
    api -->|"Start processing"| temporal
    temporal -->|"Run processing"| kfw
    kfw -->|"Read original / submit result"| api
    kfw -->|"Write extracted content and vectors"| artifacts
    api -->|"Publish accepted result"| facts

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class ui,api,kfw fred
    class temporal,artifacts,facts cots
```

<a id="13-coordinating-document-writes"></a>

Control Plane controls publication: producing an artifact does not by itself
make it available. Document placement, lifecycle and publication state determine
which results can be exposed. The
[document journey](02.2-document-journey.md#concurrent-imports-and-publication)
explains the coordination of concurrent imports and publication; the
[open performance question](A10-open-issues.md#oi-1-document-write-concurrency)
records the evidence needed to assess its cost under load.

## 1.3. Agents: accessing knowledge during a conversation

The Agent Pod resolves the user's authorized execution context with Control
Plane for each turn. When the assistant needs documents, it invokes a capability
that calls Knowledge Flow API on the user's behalf, using their delegated
identity and the space bound to that turn.

<a id="15-document-search-during-a-conversation"></a>

```mermaid
flowchart TB
    ui["Frontend<br/>Chat"]
    subgraph pod["Agent Pod - default: fred-agent"]
        agent["Assistant execution"]
        capability["Document Search capability"]
        agent -->|"Invoke tool"| capability
    end
    cp["Control Plane API"]
    kfa["Knowledge Flow API<br/>Search and content retrieval"]
    stores[("Knowledge stores<br/>Index, publication facts and content")]
    ui <-->|"Messages / streamed answers"| agent
    agent -->|"Resolve authorized turn context"| cp
    capability -->|"Delegated identity / bound space"| kfa
    kfa -->|"Resolve authorized document scope"| cp
    kfa -->|"Search / verify visibility / retrieve"| stores

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class ui,agent,capability,cp,kfa fred
    class stores cots
    class pod neutral
```

Knowledge Flow API checks the user's access to the requested space, searches
the index and verifies document visibility before returning content. The
capability stays with the agent; knowledge retrieval and storage access stay
with Knowledge Flow.

## 1.4. Governance: administering resources by space

The organization owner sets business choices, including permitted agents, models
and the capabilities each Agent Pod offers. Each person's
space roles determine what they may
manage, contribute to or read. The owner's separate institutional mandate and
the precise role boundaries are defined in the [roles annex](A11-roles.md).

```mermaid
flowchart TB
    admin["Organization owner"]
    policy["Organization policy<br/>Permitted agents and models"]
    person["Person"]
    roles["Roles in a space<br/>Read / contribute / administer"]
    space["Working space<br/>Organization, team, project or personal"]
    documents["Space documents"]
    assistants["Agent instances<br/>configured in the space"]
    admin -->|"Sets"| policy
    person -->|"Holds"| roles
    roles -->|"Determine allowed actions"| space
    space -->|"Contains"| documents
    space -->|"Contains"| assistants
    policy -->|"Constrains available choices"| assistants

    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class admin,policy,person,roles,space,documents,assistants neutral
```

An assistant must satisfy both controls: the organization's usage policy and
the person's access rights in the working space. The [security chapter](03-security.md)
defines inheritance and isolation rules.

## 1.5. Models: authorization, selection and invocation

<a id="14-model-governance-and-agent-execution"></a>

**Assistant model: selection and execution**

Control Plane maintains the model catalog and the organization's permitted
choices. The user selects an available model; the Agent Pod resolves the
authorized choice for the turn, calls the model service and streams the answer
directly to the frontend.

```mermaid
flowchart TB
    ui["Frontend<br/>Model selection"]
    cp["Control Plane API<br/>Catalog and organization policy"]
    pod["Agent Pod<br/>Assistant execution"]
    model["Generation model service"]
    ui -->|"Prepare selected model"| cp
    pod -->|"Resolve authorized model for the turn"| cp
    cp -->|"Discover model offerings"| model
    pod -->|"Generate response"| model

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class ui,cp,pod fred
    class model cots
```

**Knowledge embeddings: indexing and search**

Knowledge Flow also uses models: its worker embeds document chunks during
indexing, and its API embeds queries during search. This embedding configuration
is separate from the generation model selected for a conversation.

```mermaid
flowchart TB
    kfa["Knowledge Flow API<br/>Document search"]
    kfw["Knowledge Flow worker<br/>Document indexing"]
    embed["Embedding model service"]
    kfa -->|"Embed query"| embed
    kfw -->|"Embed document chunks"| embed

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class kfa,kfw fred
    class embed cots
```
