## Why

PR #2966 accumulated successive platform-access UI and backend iterations. Before merging, reduce implementation duplication and unrelated diff noise while preserving the working behavior at `e239bd1e3f141e029ce3ee969930552a20d8b3a9` and proving regression coverage. This is local-only follow-up to #2965; do not push or update GitHub.

## What Changes

- Remove proven unused state, CSS and translations; consolidate repeated copy-action rendering, hook exports, condition selection and SQL search predicates.
- Remove the unused selected-claim fingerprint and redundant authority reads after checking callers. Preserve observation freshness, locked reprojection, actor safeguards, transaction boundaries and public responses.
- Reduce unrelated translation reordering and punctuation churn in the PR. Preserve feature wording and functional integrations.
- Measure net application-code reduction separately from tests, generated code, documentation, archives and binary screenshots. Moving code is not a reduction. Keep meaningful test coverage and historical OpenSpec archives.
- Establish before/after behavior evidence, run all root test suites and quality checks, explicitly enable the PostgreSQL concurrency cases, and execute authenticated Playwright journeys with local screenshots. Use real services for end-to-end evidence; label isolated component tests separately.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a behavior-preserving refactor of `platform-access-control`; `skip_specs: true` avoids manufacturing a new requirement. Existing specification scenarios are the acceptance contract. Any discovered change to those semantics needs separate approval.

## Impact

Primary areas: `apps/frontend` platform access pages and RTK aliases, `apps/control-plane-backend/platform_access`, and `libs/fred-core/security/platform_access`. The unused fingerprint may also be removed from the PR's single pending migration and model. Existing migrated databases may retain the inert nullable column; do not destructively rebuild the user's database.

No new dependency, endpoint, admission feature or deployment setting. Preserve generated API shape, regenerate if schema imports change, and review shared consumers before changing any common UI behavior. Existing issue #2965 and PR #2966 remain the tracking context, without remote writes during this exercise.
