# Nova: isolated Swift/Weaver coexistence fixture

This bundle starts the coexistence exercise with a new organization in Weaver.
It does not transfer any Swift user, permission or content. It uses the existing
provisioning importer, independently of the Acme/Globex demo.

| Account | Nova | Pilote team |
| --- | --- | --- |
| `nova.admin` | `organization_admin` (technical administration) | No role |
| `nova.responsable` | `owner`, `member` (responsibility and parent content membership) | `owner` |

Every new organization needs both an admin and an owner. Reusing the responsible
person at both levels keeps this fixture at two accounts. The explicit organization
`member` role satisfies the team's direct parent content-membership requirement.
`owner` alone is governance only and does not grant content access, on either Nova
or Pilote.
Neither account has a platform role. Your separately bootstrapped platform admin
imports the bundle and receives no Nova role from it.

There is exactly one organization (Nova), one team (Pilote) and no project.
The bundle includes no personal spaces, agents, models, documents or conversations.
Both accounts have the **local test password** `Azerty123_` and distinct
`nova.<role>@nova.example` email addresses. These credentials are for the local
exercise only.

## Generate, without importing

From the Weaver repository root:

```sh
make bundle-migration
```

The output is `apps/control-plane/target/nova-migration-bundle.zip`. This target
also works from `apps/control-plane`, where the output is relative to that directory.
An absolute output path can be supplied with
`MIGRATION_BUNDLE_FILE="/path/to/nova-migration-bundle.zip"`.
Only Python 3 is needed. Generation does not contact Fred, PostgreSQL or Keycloak.
The same atomic packager serves the demo and Nova; the fixtures remain separate.
The five JSON files follow the existing version-2 contract. Its required manifest
value `source_platform: "swift"` identifies the accepted wire format, not the origin
of these synthetic accounts.

## First manual exercise in Chrome

1. Before the first import, check the shared SSO directory for both usernames and
   email addresses, and Weaver for an existing Nova organization. Start with absent
   identities and organization to demonstrate fresh provisioning. The importer
   reuses existing usernames and preserves their passwords; generation does not
   check the live directory. A repeated import is additive, not a reset.
2. Open `http://weaver.localhost:8088` in a dedicated Chrome profile or a fresh
   private session. Sign in with the intended platform-admin identity, complete
   Weaver bootstrap if necessary, then accept its terms. Confirm the displayed
   identity and Weaver URL before opening **Provisioning**.
3. Select `nova-migration-bundle.zip` and import it once. Check the successful
   report and the Nova/Pilote hierarchy. Do not import the Acme/Globex demo for this
   exercise.
4. In a separate session, sign in as `nova.admin`, accept this account's terms,
   and check Nova's technical administration. It has no business role in Nova or
   Pilote and no platform administration.
5. Start another isolated session as `nova.responsable`, accept its terms, and
   check the owner role on Nova and on Pilote, plus member on Nova. It has no
   platform administration.
   An owner-only role on Pilote does not authorize reading agents or conversations.
   Selecting Pilote from Home now opens its Weaver membership management page.
   Verify that the responsible person is checked as Owner only on Pilote and that
   Member/Editor remain unchecked. The sidebar must not load its conversations.
   Entering management changes no grants. Do not toggle roles in this first exercise;
   a checkbox applies its individual grant/revocation immediately.
6. Stop here. Do not create projects, upload documents or start conversations.
   This exercise needs no Nova model configuration or search compatibility change.

Close **all** private windows between accounts, or use separate Chrome profiles;
private windows share one private session. Provider logout can also end the Swift
SSO session when using the same browser profile.

Import creates identities in the **shared SSO**, so Swift's identity directory can
also see them. Weaver role assignments are separate. This fixture neither grants
nor removes Swift application rights; do not sign these accounts into Swift during
this first exercise. The prefix avoids the checked-in demo names, not arbitrary
pre-existing production identities.

Bundle generation and local archive checks do not validate this deployed browser
journey. Validate it step by step on the installed Weaver before expanding the
exercise. Generating/importing the fixture needs no rebuild on an instance with
provisioning.
The Weaver team-management UI and its roster endpoints require the updated frontend
and Control Plane images; validate that journey after deploying those images.

The offline regression `blueprint::tests::nova_fixture_satisfies_parent_content_membership`
parses these files and checks the parent-role prerequisite with the domain role
predicate. It does not replace the manual import exercise.
