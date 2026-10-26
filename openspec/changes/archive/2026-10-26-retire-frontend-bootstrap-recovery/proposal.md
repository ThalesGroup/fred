## Why

The three first-release packages are published and a separate read-only run has verified their exact registry archives, provenance, and consumers. The repository still carries first-release bootstrap, partial-recovery, and verification-continuation controls that are no longer appropriate as active operator paths. Retiring them now reduces incident-specific code without making routine independent releases or OIDC publication a prerequisite.

## What Changes

- **BREAKING (operator/CLI inputs):** Retire the `publish-bootstrap`, `recover-bootstrap`, and `verify-existing` dispatch choices and recovery/continuation CLI options and commands. Keep `.github/workflows/Publish-frontend-packages.yml` at its existing path, restricted to `swift`, with a preparation-only dispatch and candidate/application compatibility validation. Remove publication jobs, the bootstrap-token reference, and OIDC write permission from this interim workflow.
- Delete `libs/frontend/release/bootstrap-recovery.json` and `libs/frontend/release/registry-verification-continuation.json` after removing every live reader, including the unconditional recovery-plan read in `check-release-contract.mjs`. Retire exclusive bootstrap/recovery/continuation scripts, npm/Makefile commands, workflow paths, fixtures, and tests; retain genuinely shared archive and registry metadata helpers.
- Preserve the private producer workspace, confirmed package coordinates, proposed release contract, candidate preparation and immutable archive/evidence checks, generic exact-registry verifier, and all token/UI/SDK archive and isolated-consumer guarantees. Retired CLI flags must fail clearly rather than silently selecting a weaker path.
- Keep a compact, durable historical record of the initial and partial publication identities and the successful verification run, without recreating incident configuration under another active filename. Simplify the current runbook; keep the broader [frontend packaging RFC](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md) open for later publication policy, FRED adoption, and external adoption.
- Plan independent package releases and direct OIDC publishing in a separate change. This interim cleanup neither publishes a package nor modifies npm/GitHub settings, versions, dist-tags, application code, or RAGS.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Explicitly retire the predecessor's completed first-release gate and incident-dependent CI-selection requirement, replacing them with preparation-only operation, preserved generic verification/historical evidence and adoption policy, and active-input CI selection. The implemented predecessor requirements have been synchronized into the [main specification](../../specs/frontend-package-archives/spec.md) by the installed sync workflow; [its change](../add-frontend-package-release-foundations/specs/frontend-package-archives/spec.md) remains active with task 12.7 unchecked. This cleanup is a successor delta, not a parallel release contract.

## Impact

- Workflow: `.github/workflows/Publish-frontend-packages.yml`; no workflow rename or replacement.
- Producer: the two incident JSON files, `libs/frontend/scripts/{bootstrap-publish,bootstrap-recovery,bootstrap-recovery-contract,recovery-artifact,registry-verification-continuation,registry-verifier,check-release-contract,package-inputs}.mjs`, `libs/frontend/package.json`, `libs/frontend/Makefile`, and affected CI-selection, release, verifier, metadata, and fixture tests. Exact deletion decisions and retained shared functions are in `design.md`.
- Documentation: `libs/frontend/RELEASE.md`, related package-command guidance, and a compact historical evidence record; no copy of the RFC.
- Tracking: [ThalesGroup/fred#2630](https://github.com/ThalesGroup/fred/issues/2630) remains the open predecessor issue. The GitHub issue search found no issue specifically covering this retirement; no new issue is created by this planning change.
- Predecessor reconciliation: successful [run 34890367123](https://github.com/ThalesGroup/fred/actions/runs/34890367123), attempt 1, and artifact `10365859307` support completion of verification tasks 14.7 and 17.6, recorded in predecessor `tasks.md`. Task 12.7 remains unchecked because that evidence does not establish later Trusted Publisher configuration or temporary-token revocation. Synchronizing implemented requirements did not mark that task complete or archive the change. At close-out, synchronize/archive the predecessor before synchronizing this retirement delta so an older requirement cannot overwrite the cleanup.
