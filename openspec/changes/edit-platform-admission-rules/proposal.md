## Why

Platform administrators need to adjust admission through ordinary conditions rather than editing deployment regexes. Refusal and enrollment should reuse the existing frontend `contactSupportLink` instead of introducing another support setting.

Tracking: #2965 and draft PR #2966, on the standalone `feat/platform-access-control` branch. This extends the archived initial admission change and the existing capability.

## What Changes

- Discover selectable claim paths automatically from verified human access tokens, exposing names and supported types to platform administrators without collecting other users' claim values.
- Add an admission editor with multiple conditions, one `all` (AND) or `any` (OR) combination, literal equality/inequality and contains/not-contains operators, optional case sensitivity, and bounded whole-value regex matching.
- Preview a draft against the acting administrator's verified token, explain missing or incompatible claims, and refuse active changes that would remove their last admission source.
- Persist the active rule in the shared admission authority. Changes take effect across services on subsequent requests, including with cached tokens. Deployment settings initialize a policy once and never overwrite administrator edits at restart.
- **BREAKING:** remove `platform_access.supportLink`, its Helm counterpart and public `FrontendConfig.supportLink`; use the existing static `properties.contactSupportLink` on all support consumers. Existing `jwt_claim`/`accepted_regex` settings become an optional initial rule, preserving their case-sensitive whole-value semantics.
- Preserve independent user/T0/team/Free sources, suspension, CGU, revocation, and disabled feature behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: replace deployment-owned matching with live administrator-owned rules, automatic claim discovery, preview, and shared support configuration.

## Impact

- Shared security: verified token facts, bounded predicate evaluation, cached/direct/delegated principal handling and shared asynchronous SQL authority.
- Control plane: existing platform-access API, policy storage/revisions, name-only claim catalog and administrator lockout safeguards. Extend the PR's single admission migration rather than adding a second revision.
- Frontend: existing admission administration, literal/operator editor, claim selection, preview, conflict handling, both locales and generated client; remove the support override from public config/loading.
- Deployment/docs: optional initial-rule settings in YAML/Helm/SDK configuration, regenerated schemas and an updated operator guide. Actual admission values stay in private overlays or administrator state.

## Non-Goals

Nested Boolean expression trees, arbitrary code/expression execution, numeric/date comparisons, whole JWT persistence, displaying other users' personal claim values, new roles and changes to IdP provisioning are outside this change.
