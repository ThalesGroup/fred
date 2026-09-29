## Why

ReAct and DeepAgent executions need renewable authentication while remaining subject to the person's current permissions and account status. Their authority and execution lifetime must end with the attended response, including supported child agents.

## What Changes

- Authenticate delegated service calls with a workload access token and a plain `person`, `run`, `agent` grant. A shared provider supplies the grant after checking run liveness, and the shared HTTP authentication adapter is the only source of each request's workload bearer; execution state contains no person's bearer or refresh token.
- Admit runs locally, check account status and team authorization, and resolve managed bindings through a read-only lookup carrying the grant.
- Bind attended execution to its HTTP response on both streaming APIs. Completion, human pause, detected disconnect, failure and cancellation end the run, its descendants and its credential access. Human answers receive fresh admission.
- Propagate `authority_lost`, `cancelled` and `delegation_unavailable` as typed terminal reasons through ReAct, DeepAgent and capability tools. Delegation imposes no run-duration, child-count, concurrent-run-count or record-age limit.
- Validate grants against the verified caller role, audience, issuer and token purpose, and reject grant values containing `*` or `#`. Apply the asserted person's permissions and keep directly authenticated endpoint policies explicit.
- Refuse an asserted person on control-plane routes that present the caller's bearer to another service, and make no such call when preparing managed execution for an asserted person.
- Preserve ordinary service identities' own-bearer execution and service-role shortcuts. Delegation caller-role holders receive no service-role shortcut.
- Enforce account status whenever either delegation direction is enabled, with one check per authenticated request for every subject and an account status check before every tool call of a delegated run. Platform deletion suspends the person before deleting the identity-provider account and preserves other authorization relations.
- **BREAKING** Report decided permission and account status refusals as HTTP 403 and unavailable account status decisions as HTTP 503, with bounded diagnostics.
- Provide shared first-party security configuration and an isolated tool-mount bridge that carries verified grants outside model-controlled arguments.
- Expose bounded token and delegation metrics, safe execution diagnostics, one access-log line per request, explicit local configuration overlays, and documented deployment and secret-rotation requirements.
- Preserve worker configuration, startup credential validation, transport-error polling behavior and existing scheduler/task contracts.

## Capabilities

### New Capabilities

- `delegated-execution-grant`: renewable credentials, local admission, streaming lifetime, typed stops, tool authentication, operational signals and compatibility.
- `delegation-subject-and-account-status`: caller/subject separation, current permissions, service identities and platform-owned account status.
- `authorization-denial-diagnostics`: transport status, bounded details, denial logs, account status audit events and the managed admission permission audit event.
- `first-party-app-security`: shared configuration, grant declarations and isolated tool-mount authentication.

### Modified Capabilities

None.

## Impact

- Shared security and pod libraries: token acquisition, grant verification, account status, configuration and diagnostics.
- Runtime and SDK: per-call credential providers, run scopes, both streaming APIs, typed errors and managed request schemas.
- Control plane and knowledge backend: delegated receiver endpoints, service-identity policies, account lifecycle and worker startup.
- Frontend: generated contracts, request ownership, stream abort and error handling.
- Deployment: compatible authorization model, trusted workload clients, receiver configuration, ingress protection, encrypted transport and workload secret rotation.
- Documentation and generated schemas: execution/product contracts, security and operations guides, runtime/receiver clients, configuration and chart schemas.
