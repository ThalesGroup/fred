## Context

See proposal.md. Native summarization can retry a model wrapper before its
post-success message updates are committed. Capability filesystem consumers
share the Deep backend but currently check only the requested virtual path.

## Goals / Non-Goals

Preserve the approved invocation rules through retries and alternate filesystem
consumers. No new permissions, routes, persistent tables, model calls or model
configuration. Skill output quality and changes to grill-me's procedure are
outside this repair.

## Decisions

- Keep pin observation identity in the existing invocation/graph message state,
  available to native recovery before another model attempt. Preserve the status
  before inference. Avoid middleware-instance sets, which would mix concurrent
  graph namespaces and fail across replicas.
- Apply the existing ordered filesystem permission rules to requested and
  resolved virtual targets, including system-origin skill access, before reading.
  Reuse DeepAgents' native permission-resolution helper in this adapter boundary
  and offload filesystem resolution from the event loop. The installed backend
  has no public resolver; its public glob operation recursively scans the parent,
  making a lookup per read unnecessarily expensive. A focused native-versus-port
  regression guards the dependency on that helper. Avoid duplicating resolution
  rules or treating every alias as invalid.
- Test actual native recovery and the real capability concat consumer. Scripted
  prompt assertions alone do not establish either boundary.
- Preview authorization uses the same complete eligible catalog as discovery;
  only the user command list filters user-invocable entries. Agent-only does
  not imply that its successfully loaded instructions are hidden from users.
- Map editor choice identities on every document transaction and retain only
  those matching the current canonical token. This prevents history inversion
  from mapping stale offsets after controlled clear/restore without masking an
  invalid position. Verify real hook/composer/editor composition and undo/redo.

## Risks / Trade-offs

- Retry state must not suppress a genuine later read: test equal pin identity
  within recovery separately from distinct pins, threads and child namespaces.
- Resolution can cross mounted backends: preserve ordinary permitted aliases,
  missing-file errors and system access outside the skills mount.
- The native resolver is private: keep its use local to the existing Deep
  compatibility adapter and cover mounted target/error semantics in tests.
- All work remains bounded by existing catalog/update limits. No request-wide
  network call or shared process state is added; configured clients are reused.

## Migration Plan

No migration or activation step. Deploy the runtime correction with the existing
skills configuration. Reverting the runtime commit restores the previous code.
