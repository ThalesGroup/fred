# iframe SDK compatibility inventory

The canonical protocol source is
`apps/frontend/src/rework/features/applications/applicationProtocol.ts`. Package generation copies
that allowlisted file and records its hash; there is no maintained package-side wire definition.

Current FRED callers retained by this slice:

- `applicationHost.ts` re-exports established protocol constants, frame parser, and public host
  types while retaining frame-target resolution and the host request function type.
- `applicationPath.ts` re-exports relative-path validation and retains host-owned route, chat, and
  service URL construction.
- `applicationRequest.ts` consumes the shared protected-header predicate but retains bearer and
  refresh behavior.
- `TeamApplicationHostPage.tsx` consumes the compatibility exports and remains responsible for
  source/origin checks, authorization, routing, request concurrency, and frame/team disposal.
- `TeamApplicationsPage.tsx` consumes only host route construction.
- Existing tests construct raw protocol messages dynamically and remain the legacy-client
  compatibility boundary.

The source-tree extension adds optional resolved light/dark theme and later locale/theme context
events through the canonical protocol. The published `0.1.0-alpha.1` SDK does not expose `onContext`.
The four-way published/new SDK and pinned/extended host matrix passed locally, including published
archive integrity, npm signature, and Sigstore identity checks. This supports retaining protocol
`"1"`; it is not publication evidence for the new extension. Consumers own missing-theme fallback
and translations; deployment configuration supplies exact `hostOrigin` separately, and
`?theme=&locale=` iframe query values are not an authoritative channel.

The current transport is buffered text/JSON over ordinary HTTP(S) origins. Opaque or `null` origins,
streaming, binary bodies, remote cancellation, and automatic mutation retries are not implemented.
