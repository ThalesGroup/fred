# Control-plane source map

Start with the [arc42 question map](../../../docs/architecture/README.md#find-a-function).
This file locates implementation owners; it does not duplicate their contracts.
Paths in the frontend column are relative to `apps/frontend/src/`.

| Question / responsibility | Rust owner | Frontend entry or consumer | Focused evidence |
| --- | --- | --- | --- |
| Validate an authenticated caller | [shared authentication](../../../libs/fred-rust-sdk/src/security/authentication.rs), [onboarding.rs](onboarding.rs) | `security/AuthContext.tsx` | `tests/integration.rs` |
| Accept current CGU | [onboarding.rs](onboarding.rs), handlers in [api.rs](api.rs) | `rework/core/guards/OnboardingGuard.tsx`, `rework/components/pages/GcuPage/GcuPage.tsx` | `tests/integration.rs`; `OnboardingGuard.test.tsx` beside the guard |
| [Independent platform initialization with shared SSO](../../../docs/architecture/A6-security.md#independent-platform-initialization) | [onboarding.rs](onboarding.rs), [bootstrap.rs](bootstrap.rs), handlers in [api.rs](api.rs) | `rework/core/guards/OnboardingGuard.tsx`, `rework/components/pages/BootstrapPage/BootstrapPage.tsx` | Bootstrap cases in `tests/integration.rs`; `app/Onboarding.test.tsx`; `OnboardingGuard.test.tsx` |
| Select platform versus business navigation | [platform.rs](platform.rs), [api.rs](api.rs) | `rework/core/guards/ManagerArea.tsx`, `rework/components/shared/layouts/Sidebar/AdminNavbar/AdminNavbar.tsx` | `ManagerArea.test.tsx` beside the guard |
| Read/save personal display choices | [user_preferences.rs](user_preferences.rs), `0001_schema.sql` (`users_preferences`) | `app/userPreferences.ts`, `UserSettingsPage` | `tests/support/user_preferences.rs`; `app/userPreferences.test.ts` |
| Read/replace/remove the caller's profile photo | [user_avatar.rs](user_avatar.rs), `0025_user_avatar.sql`, shared [content cleanup](documents/cleanup.rs) | `UserSettingsPage`, `UserProfile`, personal-space navigation; generated Control Plane client | Image validation and OpenAPI fixtures; functional reception pending |
| Search owner/admin accounts | [users.rs](users.rs), [keycloak.rs](keycloak.rs), `search_organization_candidates` in [api.rs](api.rs) | `rework/components/pages/admin/OrganizationsPage/OrganizationsPage.tsx` | `tests/support/organization_console.rs`; `OrganizationsPage.test.tsx` |
| Create/list organizations | `create_managed_organization` in [spaces.rs](spaces.rs), [api.rs](api.rs) | `rework/components/pages/admin/OrganizationsPage/OrganizationsPage.tsx` | `tests/support/organization_console.rs`; HTTP fixtures in `tests/support/mod.rs` |
| Import a provisioning ZIP | [blueprint.rs](blueprint.rs), [provisioning.rs](provisioning.rs), [keycloak.rs](keycloak.rs) | `rework/components/pages/admin/ProvisioningPage/ProvisioningPage.tsx` | `tests/browser_provisioning.rs`, `tests/fixtures/import_export/demo_provisioning/` |
| Resolve organization and accessible spaces | [spaces.rs](spaces.rs), [db.rs](db.rs), [authorization.rs](authorization.rs) | `slices/controlPlane/controlPlaneApiEnhancements.ts`, `rework/components/shared/layouts/Sidebar/HomeNavPanel/HomeNavPanel.tsx` | `tests/support/resource_browsing.rs` |
| Create a team/project or open personal space | [spaces.rs](spaces.rs), handlers in [api.rs](api.rs) | Personal entry in `rework/components/shared/layouts/Sidebar/HomeNavPanel/HomeNavPanel.tsx`; no connected team/project creation form | `tests/integration.rs`, `tests/support/resource_browsing.rs` |
| Query recorded consumption | [analytics](analytics/mod.rs) validates/authorizes and shares reads; [journal reader](sessions/usage/read.rs) owns aggregation; [history port](analytics/history.rs) isolates [OpenSearch](analytics/opensearch.rs) | Operator pipeline and explicit-organization `TeamUsagePage` adapter through generated RTK `queryAnalytics`; shared UI context raccord pending, collective dashboards unchanged | `tests/support/usage.rs`, planner tests and frontend `partition.test.ts` |
| Authorize a business route (404, 409, 403) | `load_facts`, `decide` and `authorize` in [authorization.rs](authorization.rs); `spaces::authorized_mutation` retains the organization lock for writes | Every business consumer, through the generated client | `business_routes_share_one_authorization_answer` in `tests/integration.rs` |
| Browse Resources / create folders | Listing: `entries` and `summary` in [documents/http.rs](documents/http.rs), [documents/reads.rs](documents/reads.rs); mutations: `create_folder` in [spaces.rs](spaces.rs), `rename_folder`/`delete_folder` in [api.rs](api.rs), [db.rs](db.rs) | `rework/components/pages/TeamResourcesPage/DocumentWorkspace/DocumentWorkspace.tsx`, `rework/components/pages/TeamResourcesPage/CreateFolderModal/CreateFolderModal.tsx` | `tests/support/resource_browsing.rs`, `tests/support/folder_scaling.rs`, `tests/support/browser_resources.rs`; `DocumentWorkspace.manager.test.tsx` |
| Manage team/project memberships without content rights | [space_members.rs](space_members.rs) for roster/candidates; [spaces.rs](spaces.rs) for existing grants/revocations | `TeamLandingPage`, `TeamSettingsPage`, `TeamContentNavbar` | `owner_only_team_membership_governance`; frontend page and sidebar tests |
| Evaluate roles and parent relationships | [roles.rs](roles.rs), [authorization.rs](authorization.rs) | Generated authorization queries, no independent frontend grant authority | `tests/integration.rs` |
| Stream the embedded Ralph agent | [embedded_agent](embedded_agent/mod.rs), [agent library](../../../libs/fred-rust-agent/src/lib.rs) | None; direct HTTP call | [manual call](../agent/README.md); execution not yet validated |
| Discover runtime agent definitions and change organization defaults | [agents.rs](agents.rs), command in [main.rs](main.rs) | `FeaturesPage.tsx` Agents tab; organization-scoped default switch and operator discovery CLI | `tests` module in [agents.rs](agents.rs) |
| Discover and govern pod tool/skill offers | [catalog](agents/catalog.rs), [inventory](agents/inventory.rs), [local ceilings](agents/local_policy.rs), [skills](agents/skills.rs), migrations 0001/0005 | OrganizationCapabilities, SpaceOffers, managed preparation/admission | `tests/support/pod_skills.rs`: disposable SQL upgrade, role ceilings, concurrency, unavailable/withdrawn sources; deployed acceptance remains separate |
| Administer platform model observations and organization policy | [model_catalog](model_catalog/mod.rs), [HTTP](model_catalog/http.rs), [policy](model_catalog/policy.rs), `0001_schema.sql` (`model_*`, `organization_model_*`) | Generated Control Plane client; no UI consumer | Compilation/quality only; manual M1/M2 cases in the active OpenSpec change |
| Save instance model settings and resolve trusted candidate data | [instance models](model_catalog/instance.rs), [instance HTTP](agent_instances/http.rs), [runtime resolver](agent_instances/runtime.rs) | `TeamAgentsPage/weaverAgents.ts`, existing `AgentFormBody` display; generated client | Compilation/quality only; M3 manual acceptance in the active change, no Python invocation wiring |
| Register/read/list/rename private conversation metadata | [sessions.rs](sessions.rs), `0001_schema.sql` (`session_metadata`) | Generated client only; `ManagedChatPage`/`useManagedChat` still use Swift clients | Prepared M5a cases in the active change; no functional execution |
| Prepare browser execution/history routing | [preparation.rs](agent_instances/preparation.rs), [runtime resolver](agent_instances/runtime.rs), [M3 model facts](model_catalog/instance.rs) | Generated client only; no chat wiring | Explicit public source path and private association checks; M5a manual cases |
| Manage space prompt categories and assignments | [prompts.rs](prompts.rs), [prompts/http.rs](prompts/http.rs), [prompts/categories.rs](prompts/categories.rs), `0001_schema.sql` | `PromptsPage`, `ManageCategoriesDialog`, `CategoryPicker`, `PromptSelectionChatPanel`; generated Control Plane client | `tests/support/prompts.rs`; adjacent component tests (functional validation remains separate) |
| Initialize/check the SQL schema | [main.rs](main.rs), [db.rs](db.rs), [migrations](../migrations/) | None | `tests/integration.rs` |
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

Managed MCP implementation (reception pending): [mcp_connections](mcp_connections/mod.rs),
shared offer governance in [agents](agents.rs), and `admin/McpConnectionsPage` in the frontend.
Targeted fixtures are `src/mcp_connections/tests.rs`, `tests/support/managed_mcp.rs`
and `libs/fred-runtime/tests/test_managed_mcp.py`. See the
[operating procedure](../README.md#managed-mcp-connections-reception-pending) before reception.
