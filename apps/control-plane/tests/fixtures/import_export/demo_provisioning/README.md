# Demo provisioning fixture and dependent tests

These five JSON files are the checked-in demo input to `make build-demo-bundle`.
The generated ZIP is also used by specific regression tests. Their fixed user,
space and request counts describe this fixture, not limits of the importer.
Other bundles are supported when they follow the provisioning contract.

| Test | What it checks against the demo |
| --- | --- |
| `blueprint::tests::real_make_target_supports_space_paths_and_replaces_previous_entries` | Offline test in `src/blueprint.rs`, run by `make test`: real Make packaging, paths with spaces, replacement of an old ZIP, roster and archive contents, preservation of a valid ZIP when a source file is missing. No deployed Fred or external service is used. |
| `real_keycloak_service_account_provisions_complete_bundle` | Integration test in `tests/integration.rs`: imports the real Make artifact through HTTP into disposable services and asserts identity, space and OpenFGA request counts. |
| `provisioning_browser_journey` | Browser test in `tests/browser_provisioning.rs`: builds the demo ZIP and exercises provisioning through the UI. |

When changing this fixture's users, spaces or roles, review the dependent
assertions and documented demo request counts in `docs/architecture/09-quality.md`
from the repository root. Update expectations only for the intended fixture
change; preserve the packaging, authorization and failure guarantees. See
the component README's "Import a provisioning bundle" section for the roster
and build commands.

The demo uses `organization_admin` for Oscar and Olivia (technical Admin), and
`owner` for Alice and Grace (organization Owner / Responsable) and Carl and Marc
(team Owner / Responsable). Only these four business owners can open their own
personal space. Bob, Léa and the other content-only users cannot; no personal
space is created during import. A technical admin who also receives an owner
role becomes eligible. The bundle contains 13 users, two organizations, two teams
and no project.
