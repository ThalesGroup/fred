## Context

See [proposal.md](proposal.md) for the requested behavior. On `b0d87415b`, `PlatformAccess` compiles the deployment regex at construction, the shared singleton stores its fingerprint, and `decode_jwt` caches only the selected attribute in the principal. Changing the selected path through the UI cannot work correctly with those cached principals. The active policy must move to SQL and selected extraction must happen after reading it.

`useFrontendProperties` currently overrides static `properties.contactSupportLink` with the added public `supportLink`. Both standalone admission pages already use that hook. Removing the override and duplicate fields is sufficient; the static configuration loads before authentication.

## Goals / Non-Goals

**Goals:** one authoritative live policy, predictable string operators, claim discovery without a personal-data inventory, and preservation of existing admission safeguards.

**Non-Goals:** see the proposal. The initial editor has one flat group: all conditions or any condition, without nested groups or arbitrary expressions.

## Decisions

### Shared policy and deployment initialization

Store a typed JSON policy and an incrementing revision on `platform_access_settings`, replacing the deployment fingerprint as the rule authority. A policy has `combination: all | any` and one to sixteen conditions. Each condition contains an array of claim keys, an operator, a nonempty operand, and `case_sensitive`.

Keep deployment `enabled` and the existing optional `jwt_claim`/`accepted_regex` pair. Control plane converts a complete pair to one case-sensitive regex condition only when no policy has ever been initialized. An incomplete pair remains an explicit configuration error. An omitted pair leaves the rule unconfigured and filtering inactive; activation requires a configured rule. Restarts never reapply the seed over administrator edits. Readers require initialized shared state and never substitute their local seed on a database failure.

Extend the existing admin surface with `GET /claims`, `POST /policy-preview` and `PUT /policy`; include policy/revision in state reads. Writers use the existing platform-management permission and policy transaction lock. Require the expected revision, return 409 for concurrent stale edits, and evaluate actor eligibility with the proposed rule before committing when filtering is active. Saving an invalid policy or a lockout leaves state unchanged. This avoids silent overwrites and preserves current user/team mutations.

Alternative rejected: recompiling Helm rules at each restart or keeping the active rule in process memory. Both lose edits or make replicas disagree.

### Literal and regex semantics

Support `equals`, `not_equals`, `contains`, `not_contains` and `regex`. Literal operators treat metacharacters as ordinary text and default to case-insensitive Unicode comparison, with an explicit case-sensitive option. Regex is an advanced whole-value mode with explicit case handling; converted deployment regexes retain their current case-sensitive behavior.

For a nonempty string array, positive predicates match any element; negative predicates require every element to satisfy the negation. Missing, empty, oversized or incompatible values fail every predicate, including negative ones. Both all/any modes reject an empty condition list. Literal operands are bounded to 1024 characters and regex operands to 2048. Preserve the existing 1024-character string, 32-element array and sixteen-key path bounds. Regex compilation is validated before save; matching has one 25 ms deadline for the entire policy and a timeout cannot grant rule-derived admission. Compile by immutable revision rather than caching admission decisions.

Alternative rejected: translating all literal predicates into user-visible regexes. Explicit operators keep input semantics understandable and avoid accidental regex interpretation.

### Verified facts, discovery and delegated observations

Preserve bounded normalized string/string-array facts and their unambiguous paths from verified human payloads only in the internal principal/JWT cache, excluded from serialization, repr and logs. Cap traversal and retained facts, and report an unavailable selected fact as non-matching. Do not persist the JWT or the full fact map. Evaluate the currently selected paths after reading the live policy, so a cached token follows an administrator's claim/operator change without renewal.

Discover filterable path names and supported types from those facts; persist only path/type metadata in a bounded shared catalog, never other users' values or token contents. Catalog writes are async, conflict-safe and limited to newly discovered metadata, with bounded traversal and a 256-path catalog. Workloads and unverified tokens do not contribute. The admin selector labels this as observed claims, not a complete IdP schema. It supports entering an unambiguous path when a claim has not yet been observed. Discovery failure cannot make active admission fail open.

Persist only the current policy's selected human facts and their verified token lifetime for delegated admission, extending the existing observation storage. Keep monotonic `iat`, expiry and contradiction checks. A changed predicate can reuse compatible unexpired selected evidence; a newly selected path needs fresh direct human evidence. Missing evidence fails that condition and does not become a positive result through negation. Never use workload facts for the delegated person. T0 continues to use reliable evidence under the current rule and imports unknown classifications conservatively.

Alternative rejected: persisting every user's complete claim payload to enable arbitrary future policy previews. It adds unrelated personal data; draft preview instead evaluates the actor's verified facts only.

### Editor and preview

Extend `PlatformAccessPage` using shared form components. Show claim selection, localized operator labels, operand and case handling, add/remove condition controls, and a clearly labeled all/any choice. Regex inputs have validation feedback and explain whole-value semantics. A Test action returns per-condition match/missing/type results, aggregate rule result and the actor's effective admission including exceptions. It never changes the policy, observations for a proposed path, T0 or membership.

Preview explains whether the actor would be admitted with filtering active, even when the current filter is off. Save is explicit, announces success/errors and preserves the draft on a revision conflict. Existing filtering, T0, user and team controls remain on the page. Both support screens and profile support actions use the existing `contactSupportLink`; no new backend support URL is required.

## Risks / Trade-offs

- Claim discovery is incomplete until relevant humans authenticate. Describe the observed catalog and allow manual paths without claiming an IdP schema inventory.
- Cached token facts retain additional bounded data in memory. Exclude them from every public principal/log output and persist only active-policy evidence.
- Catalog growth and matching can add authentication work. Bound collection, metadata writes, predicates, regex time and compilation caches; preserve async SQL/client lifecycles.
- New paths can remove delegated eligibility until fresh human evidence exists. Surface this limitation in the editor/operator guide and retain independent exceptions.
- Concurrent policy edits or restrictive predicates can lock out administrators. Use revisions, atomic actor checks and existing operator disablement for recovery.

## Migration Plan

Extend draft PR #2966's single `f9a2c7d81e40` migration, keeping its `aac66348e27b` parent. Add policy/revision and the name-only catalog, and update selected-evidence models without introducing a second migration. Document how to recreate an isolated database that already applied an earlier draft; do not silently stamp it or alter a developer database during implementation.

Update YAML/Helm/SDK defaults, remove duplicate support settings, regenerate schemas/client, and deploy consistent enabled readers after the control-plane authority. Existing seed configuration preserves one-rule matching; subsequent UI edits survive restart and seed changes. Roll back enforcement through the persisted filtering switch or feature disablement, retaining additive admission state. Update the existing operator guide and current contracts; leave the archived initial change as history. Reconcile and archive this follow-up after implementation and required review.
