# Developer Tools – AI-Assisted Review & Compliance

This folder provides AI-powered developer utilities to improve code quality and deployment consistency for the [Fred](https://fredk8.dev) project. It also includes a license header enforcement script.

---

## 📦 1. `ai_code_review.py` — Python Code Quality Review

This script reviews your local Python changes using GPT-4 and provides actionable feedback based on internal coding standards.

### Features
- Checks for:
  - Violations of architecture (services, controllers, utils)
  - Bad exception handling or missing validations
  - Lack of tests or docstrings
  - Poor naming or misuse of Pydantic
- References:
  - `docs/CODING_GUIDELINES.md`
  - `docs/CONTRIBUTING.md`

### Usage
Run via Make:

```bash
make review-pull-request   # Review committed changes vs origin/main
make review-uncommitted    # Review staged changes
make review-all            # Review all modified Python files
```

---

## 🔧 2. `ai_deployment_review.py` — Deployment Consistency Review

Checks whether Python config model changes (e.g., `BaseModel` fields) are reflected in the deployment configuration (Helm, YAML, etc).

### Features
- Detects renamed/missing fields between Python and deployment files
- Highlights obsolete or unreferenced fields in Helm charts
- Uses vector search and GPT to contextualize changes

### Usage

```bash
make review-deploy
```

---

## 🪪 3. `check_and_add_apachev2_headers.sh` — License Header Checker

Ensures all Python files include the required [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0) header.

### Usage

```bash
./check_and_add_apachev2_headers.sh
```

- Scans all `.py` files under the current folder
- Skips `.venv`, `.git`, `__pycache__`, and `htmlcov`
- Prepends the license header if missing

---

## 🛠️ Setup

Install dependencies with:

```bash
make dev
```

Create a `.env` file under `config/`:

```
OPENAI_API_KEY=sk-...
```

---

## 🧹 Cleanup

Remove the virtual environment and build artifacts:

```bash
make clean
```

---

## 🧭 Notes

- These tools are designed to run **from the `developer_tools/` folder**.
- `Makefile` targets handle virtualenv activation and path configuration.
- All prompts and responses use OpenAI's GPT models with structured input for consistent results.
