# Demo provisioning fixture and dependent tests

These five JSON files are the checked-in demo input to `make build-demo-bundle`.
The generated ZIP is also used by specific regression tests. Their fixed user,
space and request counts describe this fixture, not limits of the importer.
Other bundles are supported when they follow the provisioning contract.

The people, spaces and roles are described once, with the rule each person
illustrates, in [Example people and spaces](../../../../../../docs/architecture/02-journeys.md#example-people-and-spaces).
Keep that table and these files identical. The bundle contains 11 accounts,
two organizations (Acme, Globex), two teams (Research, Support) and one project
(Atlas, in Research). Every account uses the test password `Azerty123_`. No
personal space is created during import; the platform account is bootstrapped
separately.

`boss` is a test convenience account, not a persona: it holds every role on every
space of both organizations plus all platform roles. Never use it to demonstrate or
test a rule.

| Test | What it checks against the demo |
| --- | --- |
| `blueprint::tests::real_make_target_supports_space_paths_and_replaces_previous_entries` | Offline test in `src/blueprint.rs`, run by `make test`: real Make packaging, paths with spaces, replacement of an old ZIP, roster and archive contents, preservation of a valid ZIP when a source file is missing. No deployed Fred or external service is used. |
| `real_keycloak_service_account_provisions_complete_bundle` | Integration test in `tests/integration.rs`: imports the real Make artifact through HTTP into disposable services and asserts identities, space roles and platform grants. |
| `provisioning_browser_journey` | Browser test in `tests/browser_provisioning.rs`: builds the demo ZIP and exercises provisioning, memberships and personal spaces through the UI. |

When changing this fixture's users, spaces or roles, update the example table
and review the dependent assertions. Update expectations only for the intended
fixture change; preserve the packaging, authorization and failure guarantees.
