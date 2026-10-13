## Why

Platform operators need to pause admission filtering without losing their configured rules and exceptions. Platform administrators must retain access while filtering is active, and operators need to know which people actually joined through each Free-team link rather than infer that from page-opening counts.

## What Changes

- Confirm that disabling filtering immediately admits all active, authenticated people while retaining the saved rule, user and team exceptions, Free settings and links for later activation. Keep authentication, suspension, terms and resource permissions in force.
- Retire the file-based `users.txt` whitelist, its runtime gate and Helm configuration so platform admission has only the administrator-managed SQL filter.
- Admit an active platform administrator independently of rule and whitelist matches on direct and delegated human requests. Resolve the current platform-management permission from ReBAC, including after role changes.
- Record successful first-time team enrollment through a specific Free link, and expose a bounded, paginated list of those users' current first name, last name and username to platform administrators on that link's history row. Preserve this history after membership removal, link expiry or revocation; remove it when the link history is explicitly deleted.
- Keep aggregate authenticated page-opening counts distinct from successful joiners. Do not record visitors or failed/repeated enrollments as new joiners.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: open-access preservation, administrator admission, and per-link join history.

## Impact

- Shared platform admission in `fred-core` and all participating direct/delegated readers.
- Remove the legacy Helm whitelist values, ConfigMap and mount. Operators using them must move intended access rules into platform administration before upgrading.
- Control-plane enrollment, admin API, one SQL migration, generated frontend client, and link-history UI.
- The existing `platform-access-control` specification, which currently excludes visitor identity analytics; successful enrollment history is a separate, explicit administrative record.
- Tracking issue: #3061. Related original work: #2965.
