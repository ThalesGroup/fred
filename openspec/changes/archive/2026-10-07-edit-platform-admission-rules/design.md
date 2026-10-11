## Context

See [proposal.md](proposal.md) for the requested behavior. On `b0d87415b`, `PlatformAccess` compiles the deployment regex at construction, the shared singleton stores its fingerprint, and `decode_jwt` caches only the selected attribute in the principal. Changing the selected path through the UI cannot work correctly with those cached principals. The active policy must move to SQL and selected extraction must happen after reading it.

`useFrontendProperties` currently overrides static `properties.contactSupportLink` with the added public `supportLink`. Both standalone admission pages already use that hook. Removing the override and duplicate fields is sufficient; the static configuration loads before authentication.

## Goals / Non-Goals

**Goals:** one authoritative live policy, predictable string operators, claim discovery without a personal-data inventory, and preservation of existing admission safeguards.

**Non-Goals:** see the proposal. The initial editor has one flat group: all conditions or any condition, without nested groups or arbitrary expressions.

## Decisions

### Shared policy and administration-only activation

Store a typed JSON policy and an incrementing revision on `platform_access_settings`, replacing the deployment fingerprint as the rule authority. A policy has `combination: all | any` and one to sixteen conditions. Each condition contains an array of claim keys, an operator, a nonempty operand, and `case_sensitive`.

Remove the admission configuration model, YAML blocks, global Helm values and SDK environment block. In authenticated Fred deployments with enforced ReBAC, administration is available after the existing SQL migration without another enablement setting. Control plane initializes only an absent settings row, with no policy, revision zero and filtering inactive. Readers always load this shared authority and cannot use local configuration to bypass it. Saved policy and filtering survive restarts. Activation requires a valid rule and actor eligibility.

Retain existing authentication-disabled development behavior. Normal authenticated deployments use enforced account status in both directory modes, even without delegation. All participating backends initialize the shared admission reader; first-party ReBAC consumers supply their platform PostgreSQL engine. Missing/malformed authority fails closed for human requests. Pure workload operations retain their existing authorization. A nonempty legacy whitelist can remain while SQL filtering is inactive, but activation must reject concurrent gates and active readers must refuse a conflicting legacy gate.

There is no deployment disablement escape hatch. Operators recover an unavailable admission administrator by explicitly disabling the shared SQL filtering switch, then correcting the rule or independent sources in the UI. Document the required suspended-account model and shared SQL authority before deployment.

Extend the existing admin surface with `GET /claims`, `POST /policy-preview` and `PUT /policy`; include policy/revision in state reads. Writers use the existing platform-management permission and policy transaction lock. Require the expected revision, return 409 for concurrent stale edits, and evaluate actor eligibility with the proposed rule before committing when filtering is active. Saving an invalid policy or a lockout leaves state unchanged. This avoids silent overwrites and preserves current user/team mutations. Add a platform-admin-only bulk grant operation for one to 100 selected existing Fred user UUIDs. Validate the whole list before granting; unknown users reject the transaction. Existing individual sources remain unchanged. The UI retains selected IDs across searches/pages, caps selection at 100 and explicitly clears it after success. Team allowlisting reads current higher-consistency membership rather than copying members into permanent individual exceptions. Revocation of membership therefore removes the global team-derived source on subsequent requests, including other readers and cached/delegated tokens.

Alternative rejected: recompiling Helm rules at each restart or keeping the active rule in process memory. Both lose edits or make replicas disagree.

### Literal and regex semantics

Support `equals`, `not_equals`, `contains`, `not_contains` and `regex`. Literal operators treat metacharacters as ordinary text and default to case-insensitive Unicode comparison, with an explicit case-sensitive option. Regex is an advanced whole-value mode with explicit case handling.

For a nonempty string array, positive predicates match any element; negative predicates require every element to satisfy the negation. Missing, empty, oversized or incompatible values fail every predicate, including negative ones. Both all/any modes reject an empty condition list. Literal operands are bounded to 1024 characters and regex operands to 2048. Preserve the existing 1024-character string, 32-element array and sixteen-key path bounds. Regex compilation is validated before save; matching has one 25 ms deadline for the entire policy and a timeout cannot grant rule-derived admission. Compile by immutable pattern and case options in a bounded process-local cache rather than caching admission decisions.

Alternative rejected: translating all literal predicates into user-visible regexes. Explicit operators keep input semantics understandable and avoid accidental regex interpretation.

### Verified facts, discovery and delegated observations

Preserve bounded normalized string/string-array facts and their unambiguous paths from verified human payloads only in the internal principal/JWT cache, excluded from serialization, repr and logs. Cap traversal and retained facts, and report an unavailable selected fact as non-matching. Do not persist the JWT or the full fact map. Evaluate the currently selected paths after reading the live policy, so a cached token follows an administrator's claim/operator change without renewal.

Discover filterable path names and supported types from those facts; persist only path/type metadata in a bounded shared catalog, never other users' values or token contents. Catalog writes are async, conflict-safe and limited to newly discovered metadata, with bounded traversal and a 256-path catalog. Workloads and unverified tokens do not contribute. The admin selector labels this as observed claims, not a complete IdP schema. It supports entering an unambiguous path when a claim has not yet been observed. Discovery failure cannot make active admission fail open.

Persist only the current policy's selected human facts and their verified token lifetime for delegated admission, extending the existing observation storage. Keep monotonic `iat`, expiry and contradiction checks. A changed predicate can reuse compatible unexpired selected evidence; a newly selected path needs fresh direct human evidence. Missing evidence fails that condition and does not become a positive result through negation. Never use workload facts for the delegated person. Selected evidence writes re-read policy under the policy transaction lock so delayed requests cannot restore old selected paths. SQL operations have a five-second application deadline and map authority failures to 503. T0 evaluates a fixed population outside the policy lock and validates the revision before its atomic import, importing unknown classifications conservatively.

Alternative rejected: persisting every user's complete claim payload to enable arbitrary future policy previews. It adds unrelated personal data; draft preview instead evaluates the actor's verified facts only.

### Editor and preview

Extend `PlatformAccessPage` using shared form components. Show claim selection, localized operator labels, operand and case handling, add/remove condition controls, and a clearly labeled all/any choice. Regex inputs have validation feedback and explain whole-value semantics. A Test action returns per-condition match/missing/type results, aggregate rule result and the actor's effective admission including exceptions. It never changes the policy, observations for a proposed path, T0 or membership.

Preview explains whether the actor would be admitted with filtering active, even when the current filter is off. Save is explicit, announces success/errors and preserves the draft on a revision conflict. Existing filtering, T0, user and team controls remain on the page. Both support screens and profile support actions use the existing `contactSupportLink`; no new backend support URL is required.

## Risks / Trade-offs

- Claim discovery is incomplete until relevant humans authenticate. Describe the observed catalog and allow manual paths without claiming an IdP schema inventory.
- Cached token facts retain additional bounded data in memory. Exclude them from every public principal/log output and persist only active-policy evidence.
- Catalog growth and matching can add authentication work. Bound collection, metadata writes, predicates, regex time and compilation caches; preserve async SQL/client lifecycles.
- New paths can remove delegated eligibility until fresh human evidence exists. Surface this limitation in the editor/operator guide and retain independent exceptions.
- Concurrent policy edits or restrictive predicates can lock out administrators. Use revisions, atomic actor checks and explicit SQL operator recovery.

## Migration Plan

Extend draft PR #2966's single `f9a2c7d81e40` migration, keeping its `aac66348e27b` parent. Add policy/revision and the name-only catalog, and update selected-evidence models without introducing a second migration. Document how to recreate an isolated database that already applied an earlier draft; do not silently stamp it or alter a developer database during implementation.

Remove YAML/Helm/SDK admission settings and duplicate support settings, regenerate schemas/client, and deploy readers after the control-plane authority. No admission configuration is necessary. UI edits survive restart. Roll back enforcement through the persisted filtering switch, retaining additive admission state. Update the existing operator guide and current contracts; leave the archived initial change as history. Reconcile and archive this follow-up after implementation and required review.

Directory compatibility: admission supports both `user_directory: keycloak` and `local`. Signature-verified human observations maintain the minimal Fred identity/evidence row used by exceptions, T0 and delegated evaluation. The selected directory remains authoritative for its existing profile and provisioning operations. Workload authentication, enforced account status, finite OpenFGA timeouts and shared PostgreSQL remain required.
