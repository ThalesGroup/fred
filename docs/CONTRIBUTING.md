
# Contributing Guidelines

Thank you for your interest in contributing! This project is developed collaboratively by Thales and the open source community. Please follow the guidelines below to help us maintain a high-quality and efficient workflow.

- [🧑‍💻 Team Organization](#-team-organization)
  - [Roles](#roles)
  - [Communication](#communication)
- [🚀 How to Become a Contributor](#-how-to-become-a-contributor)
  - [Contributor License Agreements](#contributor-license-agreements)
- [✅ Pull Request Checklist](#-pull-request-checklist)
- [🧾 License](#-license)
- [🐛 Issues Management](#-issues-management)
- [🎯 Coding Style](#-coding-style)
  - [Code formatting](#code-formatting)
    - [Frontend](#frontend)
- [Commit Writing](#commit-writing)
  - [Common Types](#common-types)
  - [Examples](#examples)
  - [Resources](#resources)
  - [VSCode](#vscode)
  - [Clean Commit History](#clean-commit-history)
- [🎯 Pre-commit checks](#-pre-commit-checks)
- [🧪 Testing](#-testing)
  - [Recommended workflow:](#recommended-workflow)
- [📬 Contact](#-contact)


---

## 🧑‍💻 Team Organization

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

## 🚀 How to Become a Contributor

1. Fork the [GitHub repository](https://github.com/ThalesGroup/fred)
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

## ✅ Pull Request Checklist

Before submitting a pull request, please ensure:

- [ ] Your code builds and runs locally using `make run`
- [ ] You ran all tests with `make test`
- [ ] Code follows the existing style and structure
- [ ] You included relevant unit or integration tests for your changes
- [ ] The PR includes a clear **description** and motivation

A CI pipeline will automatically run all tests when you open or update a pull request. The internal maintainers will review only those MRs that pass all CI checks.

---

## 🧾 License

All contributions must be compatible with the project’s open source license (see `LICENSE` file in the repo).

---

## 🐛 Issues Management

- Use **plain English** when reporting issues or requesting features.
- Apply only the **default GitHub labels** (e.g., `bug`, `enhancement`, `question`) — do not create custom labels.
- Include:
  - Clear and concise problem description
  - Steps to reproduce (if a bug)
  - Motivation and expected behavior (if a feature)

---

## 🎯 Coding Style

- Follow the existing formatting and structure.
- Write **clear, consistent, and maintainable** code.
- Prefer readability and clarity over cleverness.
- We recommend using tools such as `prettier` in Javascript or `black` (or `ruff`) in Python to format your code.
- Please respect the conventions in effect for the following languages : PEP8 in Python and ECMAScript in Javascript

### Code formatting

#### Frontend

For the frontend part we use the [prettier](https://prettier.io/) code formatter.

With the [prettier vscode extension](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode) and by adding this to your `.vscode/settings.json` your code will format automaticaly on every file save:
```json
{
    "[typescriptreact]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "[typescript]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    },
    "[json]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
    }
}
```

You can also run it from the terminal to format all the frontend files in one command:

```sh
cd frontend
make format
```

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


---

## 🎯 Pre-commit checks

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

## 🧪 Testing

Testing is mandatory for any non-trivial change. Both unit and integration tests are run using `pytest`.

### Recommended workflow:

```bash
make run       # start the app locally
make test      # run all tests (unit + integration)
```

Ensure tests pass **before** opening a pull request.

### 🧩 `conftest.py` and Configuration for Local Testing

Both the `agentic-backend` and `knowledge_flow_backend` components include a centralized `app/tests/conftest.py` file. This shared testing convention plays a crucial role in keeping the test environments **robust, isolated, and developer-friendly**.

#### Why this matters:

- **Isolated unit testing**: Each backend runs with a minimal local configuration (no OpenSearch, Keycloak, or external LLMs). This avoids coupling unit tests with infrastructure.
- **Reliable app context**: The `ApplicationContext` is initialized with a handcrafted in-memory config (e.g., `minimal_generalist_config()` in `agentic-backend`), which provides just enough structure for testing core logic.
- **No noise from immature configs**: Since the production `configuration.yaml` files are still evolving, using a custom `conftest.py` config helps avoid boilerplate or fragile test setups.
- **Developer clarity**: The fixtures make it obvious how to initialize services, mock agents, or plug in `TestClient` with mounted routers—without needing to run the whole stack.
- **Scalable to integration tests**: You can keep using this base and extend it later with additional marks (`@pytest.mark.integration`) or Docker-based services.

#### How to use it:

- For **unit tests**, rely on the `client` or `test_app` fixture in `conftest.py` to get a ready-to-use FastAPI client.
- For **controller or agent logic**, use the initialized context and override only what’s necessary.
- When needed, you can mock service behavior using `monkeypatch` or swap components like `AIService`, `SessionStorage`, etc.

By following this pattern consistently in both backends, we ensure clean separation of concerns, easier debugging, and faster CI iterations.

---

## 📬 Contact

For coordination or questions, please contact the internal maintainers:

- romain.perennes@thalesgroup.com
- fabien.le-solliec@thalesgroup.com
- dimitri.tombroff.e@thalesdigital.io
- alban.capitant@thalesgroup.com
- simon.cariou@thalesgroup.com
- florian.muller@thalesgroup.com
