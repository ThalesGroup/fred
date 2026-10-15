# Fred business journey and organization boundaries

This map is the checklist for reconstructing Fred one complete business journey
at a time. It identifies decisions that must be resolved before exposing an entry
point, not a promise that the whole Python product runs through manager. Current
manager behavior and proofs have one home: [the architecture dossier](../../architecture/README.md).
Buildable deltas belong in OpenSpec; work tracking belongs in issue #3092 and its
follow-ups. Before each slice, trace its predecessors and affected successors here.

## First journey

1. An operator deploys manager and the matching frontend, auth configuration,
   legal text/version and a bootstrap secret. A failed startup is visible and retryable.
2. A person authenticates with their own Keycloak credential. This creates neither
   organization membership nor platform authority.
3. The person explicitly accepts the active CGU. Consent records only subject,
   version and time. It never enrolls in default teams or accepts for somebody else.
4. On a fresh platform the person supplies the bootstrap secret and becomes root.
   No organization, team or personal space is created. Root is not an organization admin.
5. Root imports the Make-generated provisioning ZIP. The declared identities,
   organizations, teams, projects and roles are reconciled; the UI reports server
   acknowledgments. Errors preserve explicit repair/replay rather than claim rollback.
6. Root signs out. An imported person signs in, personally accepts CGU, and sees
   only their own declared memberships. Import does not pre-accept their terms.

Acceptance is automated with `make -C apps/frontend test-provisioning-browser`:
real UI, OIDC, manager, PostgreSQL and OpenFGA, empty initial state, no fabricated
Python shell. Unit/contract/integration checks exercise failures and concurrency
before this complete journey. A human can then repeat this same journey in k3d;
a one-off curl is not the feature acceptance criterion.

## Product inventory to examine before extending the journey

For every row, decide the owner and organization/team/project boundary before
implementation. Preserve supported roles and failure semantics; stop and discuss
any need for an ad hoc compatibility layer. Existing Python behavior is evidence
to reconcile with the agreed model, not a reason to copy implicit enrollment.

| Journey or concern | Questions that affect organization scope | Existing entry point to inspect | Repeatable acceptance boundary |
| --- | --- | --- | --- |
| Authentication and identity lifecycle | Issuer/subject mapping, service identities, disabled/deleted accounts, token expiry, logout, password/reset/MFA and profile data ownership | `fred_core/security/oidc.py`, Keycloak configuration, control-plane `users/` | Fresh login, revoked/expired credentials, account switch without cached data leakage |
| Admission | Platform access, allowlist, self-registration, invitations, approval and refusal; distinguish global admission from joining an organization | Control-plane `platform_access/`, `users/` | Invited and uninvited people, disabled account, independent org membership |
| Personal and administrator agreements | CGU versioning/localization, renewal, legal text deployment, team administrator charter and pending promotion | Control-plane `users/`, `teams/` | Updated agreement blocks access/promotion until personal acceptance; no unrelated enrollment |
| Root and platform governance | Protected root, delegated platform admins, all roles including observer, platform-wide versus org-scoped administrative visibility | Control-plane `bootstrap/`, `users/`; manager `platform.rs`, `roles.rs` | Grant/revoke under concurrency and server enforcement for direct API callers |
| Organizations and spaces | Creation, selection, naming, membership, invitation, personal space, team/project hierarchy, leaving/removal/deletion, last-admin rule, default teams | Control-plane `teams/`; manager `spaces.rs` | Two organizations with homonyms, cross-org refusals, parent/child role invariants |
| Provisioning and portability | ZIP schema, identity reconciliation, roles, project parents, replay, partial failure, export content and reset ownership | Control-plane `import_export/`; manager `blueprint.rs`, `provisioning.rs` | Generated bundle imported from UI, replay and rejected legacy/unsupported payloads |
| Administration and catalogs | Models/providers, credentials, capabilities/tools, application integrations, feature flags, routing policy, platform prompts and theme settings: global defaults versus org overrides | Control-plane `product/`, `capabilities/`, `applications/`, `routing_policy/`, `platform_prompt/`, `platform_ui_settings/` | Authorized settings change followed by its real consumer; isolation from other organizations |
| Discovery and distribution | Team, prompt and agent marketplaces; publishing, moderation, subscriptions, visibility, versions and ownership | Control-plane `agent_marketplace/`, `marketplace_settings/`, `teams/`; frontend marketplace routes | Publication and adoption between permitted spaces, private data remains private |
| Content ownership before ingestion | Libraries/knowledge bases, folders, document metadata, wiki and resources, inherited scope, content roles distinct from space administration | Control-plane `knowledge_bases/`, `team_wiki/`; knowledge-flow APIs; manager document/folder routes | Admin without content role cannot read; team/project isolation and allowed ancestor scope |
| Content ingestion and retrieval | Uploads/object storage, connectors, ingestion workers, indexing/vector search, citations/previews/download, deletion/repair, quotas | Knowledge-flow backend/workers; manager `ingestion.rs` | UI upload to searchable content and deletion across storage/index; retry, cancellation and revocation |
| Agents and conversations | Agent instances/tuning, prompts/tools, execution grants/delegation, team selection, streaming, history/sharing, files/artifacts and memory | Control-plane product APIs, `fred-runtime`, `fred-agents`, frontend managed-chat | Full conversation under one scope, switch organization, denied delegated access and reconnect |
| Background work | Tasks, progress/SSE, scheduling, retries, cancellation and rehydration, ownership of work started before role revocation | Control-plane `tasks/`, scheduler, Temporal and frontend tasks | Start, reconnect, cancel and inspect final result with the same authority boundaries |
| Evaluation and analytics | Analyst rights, conversation access, corpus management, evaluations, KPIs, usage/budget attribution | Control-plane `evaluations/`, `kpi/`; manager typed analyst permissions | Analyst versus ordinary admin, cross-organization visibility and aggregation |
| Communications and support | Announcements/patch-note acknowledgment, language, branding, help/contact/support, user settings | Control-plane `announcements/`, frontend help/settings/legal routes | Intended audience and per-person acknowledgments without granting product access |
| Privacy, audit and operations | Personal data export/erasure/retention, role and consent audit, health/metrics, backups/restore, schema migration, deployment/CI, secret rotation | Fred security/logging contracts, deployment chart/factory, GDPR and administration pages | Auditable effects, restore with consistent authority, rotation/restart, no leaked secrets |

The content-administrator self-assignment rule requires an explicit decision before
an editing UI relies on it. Likewise, a visible navigation entry requires its
admission, authorization, empty/error states and complete automated acceptance;
it is not enabled merely because an endpoint exists. Measure OpenFGA query types,
counts, pagination and driving cardinalities for each affected journey, as required
by [the branch instructions](../../../AGENTS.md#fred-manager-reconstruction-on-chorerust-rebac).
