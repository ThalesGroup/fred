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
