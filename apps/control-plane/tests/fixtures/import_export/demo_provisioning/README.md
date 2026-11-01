# Demo provisioning fixture and dependent tests

These five JSON files are the checked-in demo input to `make build-demo-bundle`.
The generated ZIP is also used by specific regression tests. Their fixed user,
space and request counts describe this fixture, not limits of the importer.
Other bundles are supported when they follow the provisioning contract.

| Test | What it checks against the demo |
| --- | --- |
| `blueprint::tests::real_make_target_supports_space_paths_and_replaces_previous_entries` | Offline test in `src/blueprint.rs`, run by `make test`: real Make packaging, paths with spaces, replacement of an old ZIP, roster and archive contents, preservation of a valid ZIP when a source file is missing. No deployed Fred or external service is used. |
| `real_keycloak_service_account_provisions_complete_bundle` | Integration test in `tests/integration.rs`: imports the real Make artifact through HTTP into disposable services and asserts identities and space roles. |
| `provisioning_browser_journey` | Browser test in `tests/browser_provisioning.rs`: builds the demo ZIP and exercises provisioning through the UI. |

When changing this fixture's users, spaces or roles, review the dependent
assertions. Update expectations only for the intended fixture
change; preserve the packaging, authorization and failure guarantees. See
the component README's "Import a provisioning bundle" section for the roster
and build commands.

The demo uses `organization_admin` for Oscar and Olivia (technical Admin), and
`owner` for Alice and Grace (organization Owner / Responsable) and Carl and Marc
(team Owner / Responsable). Any business role (`owner`, `member`, `editor` or
`analyst`) makes its holder eligible to open their own personal space; technical
admin alone does not. No personal space is created during import.

Priya (`priya`, demo password `Azerty123_`) is the full Acme/Research walkthrough
account: `organization_admin`, `owner`, `member`, `editor` and `analyst` on Acme,
plus `owner`, `member`, `editor` and `analyst` on Research. She can manage models
and shared spaces, read/write content, use evaluation permissions and open her
personal space. This account uses existing roles; it grants no platform authority,
Globex access or access to other users' personal content. Configured model and
capability restrictions still apply. The original personas retain their narrow
grants for role-by-role checks.

The bundle contains 14 users, two organizations, two teams and no project.
