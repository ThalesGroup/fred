## Purpose

Defines which Docker images the pull-request check builds, so that each change builds the images it can affect and releases still build all of them.

## ADDED Requirements

### Requirement: Pull requests build only affected images

The pull-request Docker check SHALL compare the PR head with its merge base on the target branch and SHALL build the union of the images selected by each changed path, deleted and renamed paths included. Selection rules SHALL live in `.github/docker-images.json`.

#### Scenario: Documentation-only change

- **WHEN** a PR changes only files under `docs/`, `openspec/` or Markdown files at the repository root
- **THEN** no image is built and the check succeeds

#### Scenario: Frontend change

- **WHEN** a PR changes only files under `apps/frontend/`
- **THEN** only the frontend image is built

#### Scenario: npm package producer change

- **WHEN** a PR changes only files under `libs/frontend/`
- **THEN** no image is built

#### Scenario: General change

- **WHEN** a PR changes a path no rule claims, such as a library, a backend other than knowledge-flow, or an unknown path
- **THEN** every image is built except knowledge-flow, unless the path is one of its inputs

### Requirement: Knowledge-flow builds only when its inputs change

The knowledge-flow image SHALL be built by a PR only when a changed path matches its declared `pr_inputs`. Those inputs SHALL cover every `COPY` source of its Dockerfile and every transitive local path dependency of its `pyproject.toml`.

#### Scenario: Library knowledge-flow does not use

- **WHEN** a PR changes only `libs/fred-sdk/`
- **THEN** the knowledge-flow image is not built

#### Scenario: New local dependency without COPY

- **WHEN** a PR adds a local path dependency to the knowledge-flow or fred-core `pyproject.toml`
- **THEN** the knowledge-flow image is built and a missing `COPY` fails the check

### Requirement: Full builds remain available

Release builds SHALL build every publishable image. A manual run of the check, or a PR whose diff cannot be computed, SHALL build every image and state why.

#### Scenario: Manual full check

- **WHEN** a developer runs `Check docker images` manually on a branch
- **THEN** every image is built

### Requirement: Selection is reported

Each run SHALL report every image as selected, with the paths that selected it, or skipped. An empty selection SHALL skip the build job without failing the check.

#### Scenario: Empty selection

- **WHEN** no image is selected
- **THEN** the build job is skipped and the run summary lists every image as skipped
