## Context

The existing SQL authority supports independent exceptions and eligible teams but refuses activation without a predicate. User rows omit first/last names; bulk grants perform individual lookups and have a product cap. The page has four retained panels with an immediate switch in Activation.

## Goals / Non-Goals

Provide recognizable people and deliberate activation, without changing resource roles, invitation validity or storing complete JWTs.

## Decisions

- Extend generated user projections with nullable first/last names; reuse team-member translation labels and DataTable. Search username, email and names consistently for listing/counting.
- Keep paging bounded while total selection is unbounded. Deduplicate UUIDs, query in batches of 500 and bulk-add missing exceptions under the existing policy lock. Any unknown identity or transaction failure rolls the operation back; existing T0/manual provenance is preserved.
- A saved rule, individual exception, or allowed/Free team enables the activation action. SQL state responses expose admission configuration availability without scanning user tokens. Without a predicate, only live independent sources admit; an entirely empty configuration cannot activate.
- A read-only activation preview explicitly scans local identity rows, selected verified evidence and live membership with bounded concurrency. It returns a checked-at time, policy revision, counts and identity classifications for a paginated DataTable view. Expired/conflicted/incomplete evidence is uncertain; independent sources still allow. No JWT inventory or shared claim catalog is created. Suspension is refused, CGU remains separately enforced.
- The floating Fred Button is present across tabs. Its confirmation Dialog uses only saved authority, warns that uncertainty needs fresh sign-in and admission revocation takes effect on subsequent requests. Confirmation rechecks configuration and the actor under the authority lock. A changed policy revision rejects stale confirmation; membership remains live on actual requests and preview is not a permanent guarantee.
- Disable confirmation during load/failure or while a preview is stale relative to the visible policy revision. Disabling filtering also requires deliberate confirmation but no population scan. Unsaved drafts are not applied implicitly.

## Risks / Trade-offs

- An explicit population preview can take time for large directories or many teams: fetch it only when activation is requested, bound concurrency and expose loading/retry errors. It reads local identity metadata and selected evidence, not other users' tokens.
- Remote membership changes cannot be frozen by a SQL lock; report the observation time and retain authoritative live admission checks and actor protection.
- Very large bulk requests remain subject to ordinary transport/resource timeouts. SQL batches bound parameter counts and rollback prevents partial grants.

## Migration Plan

Deploy matching APIs and generated UI. No new revision or deployment key; filtering stays inactive until explicitly confirmed. Existing active deployments retain their policy and exceptions.
