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

The packaging RFC's SDK API was illustrative, theme/live-locale behavior remains deferred, and the
current transport is buffered text/JSON over ordinary HTTP(S) origins. Opaque or `null` origins,
streaming, binary bodies, remote cancellation, and automatic mutation retries are not implemented.
