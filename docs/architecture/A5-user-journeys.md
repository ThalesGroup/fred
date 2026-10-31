# Reference: user journey contracts and implementation

Technical companion to the [user journeys](02.1-user-journeys.md), for Fred
developers and coding assistants. It retains admission, provisioning, directory
and folder contracts, persisted effects and links to implementation. These
contracts describe behavior; they are not a record of a manually validated run.

## From an empty platform to an organization's first user

| Step | Person and action | Visible result | What is retained |
| --- | --- | --- | --- |
| 1. Sign in | A person authenticates with the configured identity provider. | Fred opens the admission journey. A login alone grants no space access. | In local-directory mode, the authenticated person's profile is recorded in `user_identity`; Keycloak directory mode reads the provider instead. |
| 2. Accept terms | The person reads the displayed CGU and accepts the current version. | Fred continues admission. If terms cannot load, the protected journey remains closed. | `terms_acceptance` records this subject, version and acceptance time. No space or role is created. |
| 3. Bootstrap | On an unclaimed platform, that person supplies the deployment bootstrap token. | The first platform admin reaches Organizations. A wrong token does not grant ownership. | `platform_bootstrap` records the claimant and completion; the actual platform-admin role is in PostgreSQL. |
| 4. Provision | The platform admin imports a provisioning ZIP defining accounts, an organization, teams and their explicit roles. | The report shows acknowledged creations and grants, or the failed phase. | Account identities, `space` rows and permission roles/placement. Import does not accept terms for anyone. |
| 5. Change account | The platform admin signs out. A provisioned business user signs in and accepts their own CGU. | Home displays that person's accessible spaces. The organization name appears in Profile. | No automatic team, folder or personal space is created by login. |
| 6. Choose a space | The user selects an accessible team, or opens their entitled personal space. | The existing space navigation opens. | Personal-space creation, when requested and allowed, creates a `space` row and its roles. Reopening reuses it. |
| 7. Open Resources | The user opens Resources in that space. | The current directory lists its folders/documents, with loading, empty and error states. | Browsing creates nothing. |
| 8. Create a folder | A user with write permission enters a folder name and confirms. | The dialog closes after success and the directory refreshes. | One `folder` row, in the selected space and optional parent folder. No object, vector or document-processing job is created. |

Bootstrap is a one-time operation. Once completed it is not reopened by changing
the token or removing roles. An interrupted ownership grant can be retried only by
its recorded claimant. Identity and logout remain accessible during admission; Profile opens after admission;
a loading or unavailable admission response is not treated as permission.

The platform admin has governance authority, not implicit content access. The
current frontend directs platform admins to Organizations, including accounts
that also carry business roles. An organization owner also has the
existing Features entry, governed by that organization role: its Agents tab reads
Rust template discovery and organization defaults without global legacy catalog
calls. Its existing default switch and withdrawal confirmation write only the
organization's SQL default; team/personal exception editing and managed
instances are not connected by this operation. Its Capabilities tab
([`OrganizationCapabilities.tsx`](../../apps/frontend/src/rework/components/pages/admin/FeaturesPage/OrganizationCapabilities.tsx))
reads the stored per-pod inventory (`organization_capabilities`), refreshes it
once on opening for an enabled pod never observed, and on request
(`refresh_organization_capabilities`). Each offer's existing default switch and
withdrawal confirmation write only the organization's SQL enablement
(`set_organization_capability_default`); team management stays disabled. Other business destinations
retain their existing area boundary. The browser journey above therefore uses a
separate business account after provisioning. This is the current navigation,
not a claim that the platform-admin role authorizes document access.

## A platform admin creates an organization

An alternative to declaring an organization in the ZIP is the Organizations form:

1. Enter the organization name.
2. Search the Owner field by entering at least two characters, then select a
   proposed account. Repeat for the field currently labelled Organization owner
   (organization owner). The same account can be selected for both roles;
   removing one selection does not clear the other. This current behavior does
   not enforce [admin/business separation](A11-roles.md#responsibility-boundaries-and-current-enforcement).
3. Submit. The form prevents duplicate submission while the request is pending.
4. On success, Fred clears the form and refreshes the organization registry.
   On failure it displays the error and does not automatically replay creation.

The candidates come from the configured directory. In Keycloak mode, Fred searches
accounts in the realm. In local-directory mode with an OIDC
provider, Fred searches profiles previously observed after successful authentication;
it does not enumerate accounts that have never signed in. Local search matches the
typed text literally, without wildcards, as a case-insensitive prefix of the username,
first name, last name or email, and returns at most 20 profiles ordered by username. Local snapshots exclude service and delegated identities. Keycloak candidate
search returns the directory results without that additional local filtering. A search failure is not an empty successful search.
The server resolves the selected usernames again when creating the organization.

The name is stored in NFC without surrounding whitespace and must then contain 1..180
characters, without control characters.
An existing or pending-deletion organization reserves its name. An unknown or
ambiguous account, or a nominee already attached to another organization, prevents
creation. The selected people receive only the organization's owner/admin roles:
no implicit content membership, team, folder or personal space. The creator receives
no additional role simply for submitting the form.

Creating an organization alone is therefore not enough to create a folder. A
business user also needs an accessible space and write permission. The current
browser provisions teams/projects and their roles through the ZIP; their Rust
creation API exists, but the frontend has no connected team/project creation form.
See [organizations and roles](04-organizations.md) for those separate contracts.

## Provisioning the business account

The current ZIP format contains `manifest.json`, `users.json`,
`organizations.json`, `teams.json` and `projects.json`. The projects array may be
empty. The platform admin selects the ZIP on Provisioning and explicitly imports
it. The [declaration contract](A2-manager-contracts.md#provisioning-declarations)
defines required fields and limits.

The current importer requires compatible Keycloak authentication and its service
directory. It can create declared accounts; existing accounts keep their profile
and password. Generic OIDC/local directory support for candidate search and
organization creation does not extend to ZIP import. Direct roles
are explicit: an owner alone cannot read or write documents. Import never
accepts another person's terms or creates their personal space implicitly.

A successful import reports reconciled spaces and acknowledged grants. A failure
can leave remote effects already completed; it does not promise rollback. Correct
the reported cause before replaying. Replay preserves committed space identities
and does not remove grants absent from the bundle.

## Carl opens his personal space

A business owner of an active organization, team or project can open Personal
space. A technical admin role alone does not qualify; mixed admin and owner roles
do. The first opening creates the space, later openings reuse its identity.
The menu and the Control Plane require current ownership, including for an
existing personal space. Losing the last owner role removes access without
deleting data. Control Plane also checks this admission when resolving a new
agent turn; the existing policy for already admitted turns is unchanged.

The personal space belongs to the organization for governance but inherits no
organization or team content rights. Opening it does not repair revoked roles.
The existing space sidebar provides Resources. A business user may instead choose
an ordinary team on Home if their roles allow it.

## Bob opens Resources

Resources displays the selected space's current directory. The breadcrumb identifies
the destination; opening a folder changes that destination. The existing creation
controls open the folder-name dialog, at the root or inside the current folder.

| Rule | Observable behavior |
| --- | --- |
| Authority | Creating a folder requires current write permission on its space. Owner/admin alone is insufficient. The server checks permission again when submitted. |
| Name | Stored in NFC without surrounding whitespace; 1..255 characters, no `/`, `\` or control characters. |
| Uniqueness | A name must be unique in the same space and parent directory. The same name in another directory is a different folder. |
| Parent | The parent must exist in the same space. A foreign-space parent is refused. |
| Depth | At most 15 folder levels, counting a root folder as level one. |
| Pending/error | Submission is disabled while pending. A failed creation displays an error; it is not automatically retried. |
| Success | The directory refreshes. The folder remains after reload and can contain subfolders. |

Creation stores a stable folder ID, its space, optional parent, name, UUID-based
path and creation time. It creates no folder-specific role: content permissions
come from the containing space. The display name is not a storage path. Creating
an empty folder does not contact object storage, the vector index or Temporal.

The [SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue) describes
all tables; the [source map](../../apps/control-plane/src/README.md) locates the
actual form, API handler, authorization and SQL code for each step.
