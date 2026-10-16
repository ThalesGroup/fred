## Why

A person must enter their one organization after signing in, without choosing a tenant.
The current POC permits grants across organizations. This is the prerequisite to
personal-space navigation agreed with the developer, tracked under #3092 on
`chore/rust-rebac`.

## What Changes

- **BREAKING**: reject a person's second organization attachment through CLI creation,
  grants and import, including concurrent writers. Canonical roles remain in OpenFGA.
- Resolve business context from committed spaces and their canonical roles/placement;
  reject ambiguous legacy grants rather than selecting an organization.
- Enforce context alongside existing permissions on business reads and mutations.
- Enter the unique organization on `/home` without a tenant URL parameter or picker,
  preserving the existing components and presentation.
- Preserve consent, platform administration and authorized revocation repair paths.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: unique organization attachment and implicit home context.

## Impact

Manager spaces, provisioning and business authorization; generated response error
contracts; Home selection and its existing navigation links; regression tests and
arc42 chapters 2, 3, 4, 9 and technical appendices. One local reviewed commit, no push.
Personal-space creation entitlement and navigation are a subsequent lot.
