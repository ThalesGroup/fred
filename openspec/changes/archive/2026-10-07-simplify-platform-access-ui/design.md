## Context

See proposal.md. Existing verified admission facts contain only compatible strings/arrays; the full payload is not retained in principal responses. PageUnauthorized already composes PageError.

## Goals / Non-Goals

Provide a genuine self-session example and reuse the established error component. Admission rules, revocation and persistence remain unchanged; no token viewer for other people.

## Decisions

- Add an optional verified-payload output to the OIDC decoder, populated only after validation and bypassing the principal cache for this explicit view. The new admin own-claims route invokes verification and projection in worker threads. Ordinary requests retain their existing decoder/cache behavior and memory footprint.
- Return a bounded JSON projection (1024 nodes, depth 16, string/key limits, 64 KiB budget), exact selectable paths from existing fact extraction, and a truncation indicator. Own credentials are required, service/delegated principals rejected, HTTP caching disabled. No claim values enter database, audit, logs or general principal serialization.
- Fetch only when the picker opens, with zero unused query retention. Reuse Dialog's focus trapping and dismissal; JSON keys are ordinary keyboard-accessible buttons. Preserve paths as arrays, including literal dots and prototype-like keys.
- Selecting a field changes only the draft path. Explicit current-value buttons copy a string or one array element; regex values are escaped for whole-value semantics.
- Extend PageError with optional caller actions, keeping its current default action. Admission pages supply support/retry/logout without mounting MainLayout or protected API consumers.

## Risks / Trade-offs

- Oversized payloads: omit oversized values, indicate truncation and make unavailable paths unselectable.
- Personal values: only current administrator's own verified token is returned on demand; clear response and UI on close.
- Unknown fields: retain searchable observed names and manual Advanced path entry.

## Migration Plan

Deploy control-plane and matching generated frontend together. No migration or configuration change; existing filtering state remains intact.
