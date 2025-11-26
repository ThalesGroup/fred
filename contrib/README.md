# Contrib Overview

This folder holds self-contained extensions that are **not** part of the core Knowledge Flow runtime. Each project here is isolated, with its own `pyproject.toml` and Makefile, so it can be developed, tested, and deployed independently without pulling extra dependencies into the main backend.

Current projects:
- `cir/`: A standalone library-level output processor service that builds corpus/graph bundles using HippoRAG. Knowledge Flow can call it over HTTP to offload heavy library processing while keeping storage and metadata in KF.

Key principles:
- Keep deps isolated to avoid contaminating Knowledge Flow or Agentic stacks.
- Provide a clear API/contract for KF to call into (Pydantic models live in `fred_core.processors`).
- Make HippoRAG optional: when installed, it builds graphs; otherwise it exports a corpus bundle.
- Make the service stateless: KF supplies previews/metadata, the service returns bundles/updated metadata; KF remains the system of record for storage.
