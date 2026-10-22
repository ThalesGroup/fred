# Control-plane source map

Start with the [arc42 question map](../../../docs/architecture/README.md#find-a-function).
This file locates implementation owners; it does not duplicate their contracts.
Paths in the frontend column are relative to `apps/frontend/src/`.

| Question / responsibility | Rust owner | Frontend entry or consumer | Focused evidence |
| --- | --- | --- | --- |
| Validate an authenticated caller | [auth.rs](auth.rs), [onboarding.rs](onboarding.rs) | `security/AuthContext.tsx` | `tests/integration.rs` |
| Accept current CGU | [onboarding.rs](onboarding.rs), handlers in [api.rs](api.rs) | `rework/core/guards/GcuGuard.tsx`, `rework/components/pages/GcuPage/GcuPage.tsx` | `tests/integration.rs`; `GcuGuard.test.tsx` beside the guard |
| Claim the first platform owner | [bootstrap.rs](bootstrap.rs) | `rework/core/guards/BootstrapGuard.tsx`, `rework/components/pages/BootstrapPage/BootstrapPage.tsx` | `tests/integration.rs`; `BootstrapGuard.test.tsx` |
| Select platform versus business navigation | [platform.rs](platform.rs), [api.rs](api.rs) | `rework/core/guards/ManagerArea.tsx`, `rework/components/shared/layouts/Sidebar/AdminNavbar/AdminNavbar.tsx` | `ManagerArea.test.tsx` beside the guard |
| Search owner/admin accounts | [users.rs](users.rs), [keycloak.rs](keycloak.rs), `search_organization_candidates` in [api.rs](api.rs) | `rework/components/pages/admin/OrganizationsPage/OrganizationsPage.tsx` | `tests/support/organization_console.rs`; `OrganizationsPage.test.tsx` |
| Create/list organizations | `create_managed_organization` in [spaces.rs](spaces.rs), [api.rs](api.rs) | `rework/components/pages/admin/OrganizationsPage/OrganizationsPage.tsx` | `tests/support/organization_console.rs`; HTTP fixtures in `tests/support/mod.rs` |
| Import a provisioning ZIP | [blueprint.rs](blueprint.rs), [provisioning.rs](provisioning.rs), [keycloak.rs](keycloak.rs) | `rework/components/pages/admin/ProvisioningPage/ProvisioningPage.tsx` | `tests/browser_provisioning.rs`, `tests/fixtures/import_export/demo_provisioning/` |
| Resolve organization and accessible spaces | [spaces.rs](spaces.rs), [db.rs](db.rs), [fga.rs](fga.rs) | `slices/controlPlane/controlPlaneApiEnhancements.ts`, `rework/components/shared/layouts/Sidebar/HomeNavPanel/HomeNavPanel.tsx` | `tests/support/resource_browsing.rs` |
| Create a team/project or open personal space | [spaces.rs](spaces.rs), handlers in [api.rs](api.rs) | Personal entry in `rework/components/shared/layouts/Sidebar/HomeNavPanel/HomeNavPanel.tsx`; no connected team/project creation form | `tests/integration.rs`, `tests/support/resource_browsing.rs` |
| Browse Resources / create folders | Listing: [documents/http.rs](documents/http.rs) and [documents/reads.rs](documents/reads.rs); mutations: [spaces.rs](spaces.rs), [db.rs](db.rs), [api.rs](api.rs) | `rework/components/pages/TeamResourcesPage/DocumentWorkspace/DocumentWorkspace.tsx`, sibling `CreateFolderModal/CreateFolderModal.tsx` | `tests/support/resource_browsing.rs`, `tests/support/folder_scaling.rs`, `tests/support/browser_resources.rs` |
| Evaluate roles and parent relationships | [roles.rs](roles.rs), [fga.rs](fga.rs), [OpenFGA model](../openfga/model.fga) | Generated authorization queries, no independent frontend grant authority | `tests/integration.rs` |
| Apply/check SQL migrations | [main.rs](main.rs), [db.rs](db.rs), [migrations](../migrations/) | None | `tests/integration.rs` |
| Configure/start the process | [config.rs](config.rs), [main.rs](main.rs) | Public configuration handler in `api.rs` | [component commands](../README.md) |

Evidence paths above are relative to `apps/control-plane/` unless a frontend path
is explicitly named. Presence of a test is not a claim that it has passed on the
current revision.

## Contract and generated code

HTTP registration and OpenAPI annotations are in `api.rs`: one registration list
(`registrations`) serves `routes`/`router` and produces `openapi`. Document and
processing routes are registered from `documents/http.rs` and `processing/http.rs`.
`domain.rs` owns shared domain types; `error.rs` owns API error conversion;
`extract.rs` owns the path, query and JSON extractors of every route.
The frontend uses `slices/controlPlane/controlPlaneOpenApi.ts` (generated) through
`controlPlaneApiEnhancements.ts`. Change the source contract and regenerate;
do not manually patch generated types. `legacyControlPlane` is a separate preserved
client, not the implementation of the Rust routes.

## Beyond folder creation

`documents/` owns Resources directory reads (`/entries`), original upload, receipts
and storage reads. `processing/` owns
processing admission, dispatch, publication and callbacks. `lifecycle/` owns space
retirement and cleanup. The empty-folder mutation remains in `spaces`/`api`; opening Resources uses `documents`.
Their contracts are in the [documents chapter](../../../docs/architecture/05-documents.md)
and the [runtime reference](../../../docs/architecture/A1-manager-runtime.md).

The local application profile is in [deploy/k3d](../../../deploy/k3d/README.md).
Infrastructure belongs to the deployment factory. Do not infer an application
contract from an infrastructure resource name.
