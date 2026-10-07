## Why

The admission editor exposes technical JSON paths rather than recognizable token examples. Standalone admission errors also diverge from Fred's existing error presentation.

## What Changes

- Select exact claim paths in a searchable JSON tree of the signed-in administrator's verified access-token payload.
- Retain observed names/types without other users' values, and move manual path entry to Advanced.
- Offer explicit reuse of a current string or array element; preserve existing operators, AND/OR, preview, revision and save semantics.
- Reuse Fred's shared error presentation for denial, enrollment failures and admission verification failures, with support/retry/logout actions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: self-session claim selection and consistent reachable admission error screens.

## Impact

Issue #2965, PR #2966. Control-plane read-only admin API, OIDC verified-payload adapter, generated frontend client, rule editor, shared PageError and admission screens. No migration, admission-decision changes or new deployment configuration.
