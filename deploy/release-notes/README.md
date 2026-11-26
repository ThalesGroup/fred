# Operator release reports

This workflow records operator impact and produces release reports. It does not
serve as an architectural specification. Current architecture lives in the
[arc42 dossier](../../docs/architecture/README.md).

## For a pull request

Copy [TEMPLATE.md](TEMPLATE.md) to `changes/<unique-slug>.md`, replace the
placeholders, and describe the actual configuration, data, rollout and rollback
impact. All non-Dependabot PRs require a note, including documentation changes.

| Impact | Minimum release increment | Meaning |
| --- | --- | --- |
| `none` | patch | Normal deployment suffices; include a specific `no_action_reason`. |
| `minor` | minor | Extra operator action, including optional activation, is required. |
| `major` | major | Substantial incompatible change. |

Keep the required headings from the template. Set `configuration` to `none`,
`local` or `production`, with a specific `configuration_reason`. Production
configuration changes must include the corresponding chart changes. Notes must
not contain credentials or private deployment values.

The increments above apply after a stable release. Between prereleases of the
same version, advance the prerelease identifier (for example `alpha.1` to
`alpha.2`), then promote to the stable version when appropriate.

Validate from the repository root using the Python environment for fred-pod:

```bash
libs/fred-pod/.venv/bin/python scripts/migration_guides.py check-pr --base <base-ref> --worktree
```

CI validates the committed version. Published notes are immutable; add corrections
as new notes. Optional `after` entries order dependent notes; `covers` records
reviewed contributions lacking their own note.

## Prepare a release

```bash
libs/fred-pod/.venv/bin/python scripts/migration_guides.py plan --version X.Y.Z --worktree
libs/fred-pod/.venv/bin/python scripts/migration_guides.py generate --version X.Y.Z --worktree
libs/fred-pod/.venv/bin/python scripts/migration_guides.py verify --version X.Y.Z --worktree
```

Resolve coverage blockers before generating a report. Review and commit the
result in `releases/vX.Y.Z/migration.md`. Publication verifies the saved guide,
version impact and paired code/chart tags before publishing images or charts.
The workflow files and `scripts/migration_guides.py` define these checks. Both tagged
release descriptions also include the source Alembic heads from
`python3 scripts/alembic_release_inventory.py --version X.Y.Z`; this does not
report deployed database state or the Control Plane SQLx schema.

## Weaver's initial release

Weaver starts a new release history at the existing policy's `activation_base`
(`f50b9a8ea8b88cac99205e7cffd2bd9eee8eef0b`). The first target is
`5.0.0-alpha.1`: use that version in the commands above. No retrospective Swift
audit or historical contribution coverage is required. Existing notes remain in
the repository, but the first report includes only notes added after this boundary.
It describes the delivered scope, fresh-install requirements and known limits.
Upgrades from Swift or earlier Weaver installations are not supported.

Before the first tag, the report uses this fixed commit as its baseline and an
explicit version is required. Later reports use the most recent first-parent
`code/v*` release in this history, including prereleases. Tags from Swift history
before the boundary or from merged side branches are not baselines. The boundary
cannot be selected again once an earlier release exists in this line.

New contributions still need notes. Published notes remain immutable; version
progression, report freshness and paired code/chart tags on the same commit remain
publication requirements. The attached filename stays `migration.md` for the
existing workflows. These changes are scoped to the Weaver checkout; Swift keeps
its own release policy and history.
