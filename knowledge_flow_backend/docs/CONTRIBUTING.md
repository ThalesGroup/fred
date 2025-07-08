# Contributing Guidelines

Thank you for your interest in contributing! This project is developed collaboratively by Thales and the open source community. Please follow the guidelines below to help us maintain a high-quality and efficient workflow.

---

## Team Organization

This project is maintained by a core team at **Thales**, in collaboration with external contributors.

### Roles

- **Internal Maintainers** (Thales):
  - Drive architecture and major design decisions
  - Maintain CI/CD and security processes
  - Review and merge contributions from all sources

- **External Contributors**:
  - Submit issues, bug reports, and suggestions
  - Propose improvements and fixes via GitHub pull requests
  - Collaborate via discussions and code reviews

### Communication

- Internal team coordination is handled via Thales tools (email, GitLab).
- External collaboration happens via **GitHub issues and pull requests**.

---

## Repository Structure

This project uses two synchronized repositories:

- **Public GitHub** (for open source contributions):
  [github.com/ThalesGroup/knowledge-flow](https://github.com/ThalesGroup/knowledge-flow)

- **Internal GitLab** (an internal mirror of the public github repo for Thales developers):
  [gitlab.thalesdigital.io/tsn/innovation/fred/knowledge-flow](https://gitlab.thalesdigital.io/tsn/innovation/fred/knowledge-flow)

---

## How to Become a Contributor

1. Fork the [GitHub repository](https://gitlab.thalesdigital.io/tsn/innovation/fred/knowledge-flow)
2. Clone your fork and create a branch:
   ```bash
   git checkout -b your-feature-name
   ```
3. Make your changes and commit with clear messages.
4. Push to your fork and open a **pull request** on GitHub.
5. Collaborate with maintainers via code review.

### Contributor License Agreements

By contributing, you agree that your contributions may be used under the project's license (see below). If required, a formal CLA process may be initiated depending on corporate policies.

---

## Pull Request Checklist

Before submitting a pull request, please ensure:

- [ ] Your code builds and runs locally using `make run`
- [ ] Unit tests all pass `make test`
- [ ] Code follows the existing style and structure
- [ ] You included relevant unit or integration tests for your changes
- [ ] The PR includes a clear **description** and motivation

A CI pipeline will automatically run all tests when you open or update a pull request. The internal maintainers will review only those MRs that pass all CI checks.

---

## License

All contributions must be compatible with the project’s open source license (see `LICENSE` file in the repo).

---

## Issues Management

- Use **plain English** when reporting issues or requesting features.
- Apply only the **default GitHub labels** (e.g., `bug`, `enhancement`, `question`) — do not create custom labels.
- Include:
  - Clear and concise problem description
  - Steps to reproduce (if a bug)
  - Motivation and expected behavior (if a feature)

---

## Pre-commit checks

To ensure the code you are about to push is quite clean and safe, we provide some pre-commit hooks:

- Check PEP8 compliance and fix errors if possible: `ruff check --fix`
- Format the code: `ruff format`
- Detect secrets: `detect-secrets`  # pragma: allowlist secret

- Analyzer the code: `bandit`

To install the pre commit hooks on your environment after it is ready (see the `dev` target of the Makefile), type this command:
```
pre-commit install
```

Then you can test manually the hooks with this command:
```
pre-commit run --all-files
```
---

## Commit Writing

### Common Types

| Type       | Description                                                        |
|------------|--------------------------------------------------------------------|
| `feat`     | Introduces a new feature                                           |
| `fix`      | Fixes a bug                                                        |
| `docs`     | Documentation-only changes                                         |
| `style`    | Code style changes (formatting, missing semi-colons, etc.)         |
| `refactor` | Code changes that neither fix a bug nor add a feature              |
| `test`     | Adding or modifying tests                                          |
| `chore`    | Routine tasks (build scripts, dependencies, etc.)                  |
| `perf`     | Performance improvements                                           |
| `build`    | Changes that affect the build system or dependencies               |
| `ci`       | Changes to CI configuration files and scripts                      |
| `revert`   | Reverts a previous commit                                          |

### Examples

- `feat: add login page`
- `fix(auth): handle token expiration correctly`
- `docs(readme): update installation instructions`
- `refactor(core): simplify validation logic`
- `chore: update eslint to v8`

### Resources

- [Conventional Commits Specification](https://www.conventionalcommits.org/)

### VSCode

- Extension for easier commit writing : [VSCode Conventional Commits](https://marketplace.visualstudio.com/items?itemName=vivaxy.vscode-conventional-commits)
- Extansion for ruff (python linter and formatter) : [Ruff extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) 

### Clean Commit History

If your branch has a messy or noisy commit history (e.g. "fix typo", "oops", "test again", etc.), we encourage you to squash your commits before merging.

Squashing helps keep the main branch history clean, readable, and easier to debug.

Tip: Use git rebase -i or select "Squash and merge" when merging the PR.

## Contact

For coordination or questions, please contact the internal maintainers:

- romain.perennes@thalesgroup.com
- fabien.le-solliec@thalesgroup.com
- dimitri.tombroff@thalesgroup.com
- alban.capitant@thalesgroup.com