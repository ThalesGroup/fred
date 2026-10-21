## Why

The platform owner can import a bundle but has no organization registry or creation screen. The developer confirmed a platform area limited to organization governance, account pages and provisioning, separate from the unchanged business UI (#3092).

## What Changes

- Add Organisations beside Provisioning in the existing administration panel, with the existing team-administration table, fields and styles.
- List active organizations with bounded pagination; create an organization with an existing account as owner and an existing account as administrator (the same account is allowed).
- Route platform owners to this area, without mounting personal-space or business navigation/consumers. Retain shared profile, preferences, legal pages and release notes.
- Preserve the complete UI for ordinary organization users. The later link from the platform area to the owner's organization is explicitly excluded, including for people with both kinds of roles.
- Keep initial owner/admin grants distinct from content membership and preserve the existing operator command's behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: platform organization registry/creation and dedicated platform navigation within Fred.

## Impact

Manager governance HTTP routes, existing organization creation and identity-directory access, generated OpenAPI/client, frontend administration navigation/page, focused regression tests and arc42. Reuse the existing space table and direct OpenFGA grants; no schema or authorization-model migration. Scope follows the developer's 2026-10-18 instructions; the platform-to-organization exception is deferred.
