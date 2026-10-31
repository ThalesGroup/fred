# Operator release notes

This workflow records upgrade impact and produces operator guides. It does not
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

Validate from the repository root using the Python environment for fred-pod:

```bash
libs/fred-pod/.venv/bin/python scripts/migration_guides.py check-pr --base <base-ref> --worktree
```

CI validates the committed version. Published notes are immutable; add corrections
as new notes. Optional `after` entries order dependent notes; `covers` records
reviewed contributions lacking their own note.

## Prepare a release

```bash
libs/fred-pod/.venv/bin/python scripts/migration_guides.py plan --worktree
libs/fred-pod/.venv/bin/python scripts/migration_guides.py generate --version X.Y.Z --worktree
```

Resolve coverage blockers before generating a guide. Review and commit the
result in `releases/vX.Y.Z/migration.md`. Publication verifies the saved guide,
version impact and paired code/chart tags before publishing images or charts.
The workflow files and `scripts/migration_guides.py` define these checks.

## Fresh history boundary

The legacy note corpus was retired with the old documentation. The policy's
`activation_base` marks the commit immediately before this cleanup. Historical
notes remain available in Git history and already published releases.

The first release whose baseline predates this boundary still requires a reviewed
`legacy_range` declaration for that interval. The cleanup does not certify an
upgrade from an older release or bypass that guard. Review actual operator impact
when preparing that release; subsequent contributions use the fresh directories.
