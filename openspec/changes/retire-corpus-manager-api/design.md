## Context

The retired MCP's CorpusManager controller is still registered on Knowledge Flow's main HTTP router. Its service owns both mock endpoints and two real Temporal maintenance entry points. The ordinary document tree lives in a different controller and service. The generated frontend client exposes corpus-manager operations, but no handwritten frontend consumer calls them.

## Goals / Non-Goals

**Goals:** Remove the unused corpus-manager route family and its dedicated code, while keeping normal document listing, ingestion, search and filesystem behavior.

**Non-Goals:** Remove corpus documents, vectors or stored objects; remove the ordinary ingestion scheduler; remove `/documents/tree` or `/fs`.

## Decisions

1. Delete the controller and service together, rather than leaving an unmounted maintenance implementation. The controller is their only production caller.
2. Remove the dedicated revectorize/repair workflow entry points, worker registrations and activities that become unreachable. Retain scheduler primitives that have independent ingestion consumers. Before rollout, operators must allow any already-started maintenance workflows to finish; removing worker registrations while such executions are active would strand them.
3. Regenerate the frontend API client from Knowledge Flow OpenAPI. Remove endpoint matrix and validation scenarios that only exist for the deleted routes. Update active contract docs; preserve historical RFCs and archived changes.

## Risks / Trade-offs

- [An external script calls a deleted `/corpus/` endpoint] → Treat this as an explicit breaking API removal and document it in the migration note; no in-repository handwritten consumer was found.
- [A maintenance Temporal execution remains active at deployment] → Drain or finish those tasks before deploying workers without their registered workflow/activity names; rollback restores the old worker and routes.
- [A broad search for `/corpus/` matches virtual filesystem paths] → Keep `/fs` corpus virtual paths and document-tree code; remove only the corpus-manager route family and its dedicated scheduler implementation.

## Migration Plan

Check for active corpus revectorize or vector-metadata repair tasks and let them finish before deploying the new Knowledge Flow worker. Remove any automation calling `/corpus/*`. Deploy backend and frontend together; rollback both if those routes are still required. Stored corpus and vector data is unchanged by this code removal.
