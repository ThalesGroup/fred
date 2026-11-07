# 1. System overview

The [space](00-introduction.md#organizations-teams-and-projects) is a work perimeter, not a
separate deployment. Fred's components carry its identity and the user's authority
through each operation. They serve many spaces without merging their access rights.

**Legend:** 🟦 Fred · 🟨 COTS · 🟪 Extensions · ⬜ Concepts

## 1.1. Components serving the space

```mermaid
flowchart TB
    ui["Frontend<br/>Work in a selected space"]
    cp["Control Plane<br/>Rights, placement and lifecycle"]
    pod["Agent Pod<br/>Agents and capability libraries"]
    kf["Knowledge Flow<br/>Document processing and retrieval"]
    ui -->|"Manage resources"| cp
    ui <-->|"Chat"| pod
    pod -->|"Resolve authorized context"| cp
    pod -->|"Search authorized documents"| kf
    cp -.->|"Processing via Temporal"| kf

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    class ui,cp,pod,kf fred
```

Control Plane owns placement, access decisions and model governance. Agent Pods execute assistants;
Fred supplies `fred-agent`, and developers can provide other pods. Capability
libraries belong to their pod. Knowledge Flow processes documents and serves
knowledge through its API. Each backend also has background work: grouping it
here with its owner does not imply a single process or replica.

## 1.2. Importing a document

```mermaid
flowchart TB
    cp["Control Plane<br/>Accept upload into a space"]
    original[("Object storage<br/>Original file")]
    temporal["Temporal<br/>Durable processing"]
    kf["Knowledge Flow worker<br/>Extract and index"]
    result[("Object storage and search index<br/>Processing results")]
    publish["Control Plane / PostgreSQL<br/>Accept and publish result references"]
    cp -->|"Store"| original
    cp -->|"Request processing"| temporal
    temporal --> kf
    kf -->|"Write"| result
    kf -->|"Submit result"| publish

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class cp,kf,publish fred
    class original,temporal,result cots
```

<a id="13-coordinating-document-writes"></a>

File bytes live in object storage; PostgreSQL records their placement and
publication. Knowledge Flow reads the authorized original through Control Plane.
Producing a file does not publish it: Control Plane accepts the result before
exposing it. The [document journey](02.2-document-journey.md) explains the user
experience; the [storage annex](A9-documents.md) details coordination and cleanup.

## 1.3. Answering in a conversation

<a id="15-document-search-during-a-conversation"></a>
<a id="14-model-governance-and-agent-execution"></a>

```mermaid
flowchart TB
    ui["Frontend<br/>Send a message"]
    pod["Agent Pod<br/>Execute the assistant"]
    cp["Control Plane<br/>Admit user, space and selected offers"]
    model["Model service<br/>Generate the response"]
    kf["Knowledge Flow API<br/>Retrieve authorized knowledge"]
    ui <-->|"Message / streamed answer"| pod
    pod -->|"Resolve context for this turn"| cp
    pod -->|"Call selected model"| model
    pod -->|"Use document-search tool"| kf
    kf -->|"Resolve authorized corpus"| cp

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class ui,pod,cp,kf fred
    class model cots
```

The pod obtains an authorized context for each turn. Selecting an assistant or
model in the browser does not grant execution. Document search uses the person's
authority within the conversation's space and permitted ancestor resources;
it does not give the model unrestricted access. The answer streams from the pod
to the frontend. Knowledge Flow's embedding models are configured separately
from the conversation's generation model.

Organization-level policy limits which models and pod offers may be used; local
capability restrictions can narrow it. Roles in the working space determine what
the person may do. [Security](03-security.md) explains these two controls;
[journey 2.3](02.3-agent-administration.md) shows how people use them.

## 1.4. Model decisions and credentials

Control Plane selects the model at admission of each turn, using the working
space's organization policy, the assistant's recommendation and the user's choice.
Team and project execution do not introduce separate model policies.

```mermaid
flowchart TB
    owner["Organization Owner"] -->|"Permitted models and defaults"| cp
    platform["Platform configuration"] -->|"Approved sources"| cp
    cp["Control Plane<br/>Select model and connection"]
    cp --> python["Python agent<br/>Separate Agent Pod"]
    cp --> rust["Ralph - Rust agent<br/>Inside Control Plane"]
    secrets["Kubernetes Secrets<br/>Local credentials"] -.-> python
    secrets -.-> rust

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class cp,python,rust fred
    class secrets cots
    class owner,platform neutral
```

Both runtimes consume the admitted decision and verify it against their local
credential binding before calling the provider. The decision carries a credential
reference, never its value. Browser preparation exposes neither that connection
nor a secret. Startup supplies credentials; it does not fix one model for the
pod's lifetime. The [model reference](A13-models.md) connects this boundary to the
SQL schema, configuration types and runtime contracts, including Ralph's narrower
transport support.
