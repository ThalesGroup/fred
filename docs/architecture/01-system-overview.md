# 1. System overview

## 1.1. Functional overview: the native document drive

Users upload documents to their space and browse its folders and files.
Their roles determine which content they can read and where they can contribute.

```mermaid
flowchart TB
    upload["Upload documents"] --> knowledge["Native document drive"]
    knowledge --> browse["Browse folders<br/>and documents"]

    classDef default fill:#F1F5F9,stroke:#64748B,color:#0F172A
```

## 1.2. Technical view: knowledge ingestion and storage

**Legend:** 🟦 Fred · 🟨 COTS · 🟪 Extensions · ⬜ Concepts

**Control Plane** serves the document drive and receives ingestion requests.
It starts processing through Temporal; **Knowledge Flow** is the worker that
executes the pipelines and produces the stored results.

```mermaid
flowchart TB
    ui["Fred UI"] -->|"Browse / upload"| cp["Control Plane"]
    cp -->|"Start processing"| temporal["Temporal"]
    temporal -->|"Processing work"| kf["Knowledge Flow<br/>Worker"]
    kf -->|"Write results"| stores[("Knowledge stores<br/>Object storage / SQL<br/>Vector index (e.g. OpenSearch)")]
    cp <-->|"Document drive"| stores

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef cots fill:#FEF3C7,stroke:#B45309,color:#451A03
    class ui,cp,kf fred
    class temporal,stores cots
```

## 1.3. Coordinating document writes

Control Plane decides when an original or a processing result becomes available.
PostgreSQL holds its placement, lifecycle and publication state; OpenFGA holds
permissions. Their changes do not share a single transaction. Control Plane
coordinates authorization checks and publication with an organization-wide
PostgreSQL lock and version guards in OpenFGA. The lock prevents participating
mutations from interleaving between their checks and their commit; the guards
also reject stale remote writes. Together with database constraints, this
preserves current authority, lifecycle rules and shared quota reservations.

The organization lock is held for reservation and publication, including their
authorization calls, not for file transfer, extraction or embedding computation.
These sections run one at a time across the organization's teams and across all
Control Plane replicas. Document reads and standalone permission checks do not
take this write lock. Sections are intended to be short; their actual duration
and accumulated waiting depend on load and dependency latency.

The [document journey](02.2-document-journey.md#concurrent-imports-and-publication)
illustrates the guarantee. [Open Issues](A10-open-issues.md#oi-1-document-write-concurrency)
records the retained design and the evidence needed to assess its performance.
