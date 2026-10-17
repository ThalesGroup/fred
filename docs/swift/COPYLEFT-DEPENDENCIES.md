# Copyleft Dependency Audit

Fred's own code is released under the **Apache License 2.0**. This document is
the detailed, canonical record of every third-party dependency under a
copyleft license (AGPL, GPL, LGPL) that Fred has ever depended on, why it is
there, how severe the risk is, and what was (or will be) done about it.

Audience: this doc is written for the engineering team, the EDM (Arnaud), and
anyone in the open source community evaluating Fred's license posture before
adopting or deploying it. It intentionally goes into more depth than the
[README Licensing Note](../../README.md#licensing-note), which only summarizes
the current state and links here.

Tracked as `LICENSE-01`/`LICENSE-02`/`LICENSE-03` in the table below;
originated from GitHub issue
[#1939](https://github.com/ThalesGroup/fred/issues/1939).

Last updated: 2026-07-09.

## How to read this document

Copyleft risk is not about whether Fred's code *calls* a dependency's
functions — it's about whether that dependency is **distributed** as part of
what we ship, and under what terms:

- **Build/dev-only tools** (never imported by application code, never shipped
  in a deployed artifact) don't create a copyleft obligation regardless of
  their license — this is the same reasoning that lets projects use a
  GPL-licensed compiler without the compiled output becoming GPL.
- **LGPL runtime dependencies**, used unmodified and dynamically
  imported/linked, are compatible with an Apache-2.0 codebase under the LGPL's
  own linking exception — the conditions are: the library is unmodified, the
  end user can replace it with another version (true by construction for any
  plain pip package), and its license is disclosed. Whether a given function
  of that library is ever called at runtime doesn't change this analysis.
- **AGPL/GPL runtime dependencies that are actively invoked**, especially in a
  networked service, carry materially more risk and need a real remediation
  decision (migrate, obtain a commercial license, or a documented legal
  opinion) — disclosure alone is not sufficient here.

## Summary

| ID | Package(s) | License | Where | Severity | Status |
| --- | --- | --- | --- | --- | --- |
| `LICENSE-01` | `pymupdf`, `pymupdf4llm`, `pymupdf-layout` | AGPL/commercial; layout: PolyForm Noncommercial | Explicit Knowledge Flow PDF extra | **High** | Standard installs exclude the family; issue #3159 |
| `LICENSE-02` | `psycopg`, `psycopg[binary]`, `psycopg2-binary` | LGPL-3.0-only / LGPL-2.0-only | `fred-core`, `knowledge-flow-backend` (Postgres driver) | Low | Resolved via disclosure — no code change needed |
| `LICENSE-03` | `jwcrypto` | LGPL-3.0-or-later | Transitive, via `python-keycloak`'s `KeycloakAdmin` — `fred-core`, `control-plane-backend`, `knowledge-flow-backend`, `fred-agents`, `fred-sdk`, `fred-runtime` | Low | Disclosed, compliant as unmodified/dynamically-imported dependency. Full removal of the transitive dependency tracked separately (issue #1949), not implemented |

---

## LICENSE-01 - optional PyMuPDF family

The `pymupdf` extra and `INSTALL_PYMUPDF=true` image variant include the
PyMuPDF family only when explicitly requested. Ordinary `uv sync`, `make dev`
and the standard production image exclude it. Installed inventory checks in
`scripts/check_pdf_dependencies.py` and the image CI guard this boundary.
The lockfile retains optional packages for reproducible opt-in builds; their
presence in that file does not mean they are installed in the standard image.

At the locked 1.27.2.3 versions, `pymupdf` and `pymupdf4llm` offer AGPL-3.0 or
Artifex commercial terms. Their transitive `pymupdf-layout` package has
PolyForm Noncommercial 1.0.0 terms. Assess the entire selected family and any
commercial agreement, not just the two direct packages. Preserve their license
and notice files in optional images. This is an inventory boundary, not a
legal determination about a deployment or a claim that all Fred dependencies
are permissively licensed.

The default fast PDF path uses pypdf (BSD-3-Clause), advanced PDF extraction
uses Docling (MIT), and PPTX rasterization uses pypdfium2 (Apache-2.0/BSD-3-Clause)
with bundled PDFium and its third-party notices. Model weights and other
transitive/native dependencies retain their separate terms. Image inventories
and SBOMs must include them, without suppressing findings or stripping metadata.

See the [deployment instructions](../../apps/knowledge-flow-backend/README.md#optional-pymupdf-processing)
and [migration note](ops/migrations/3159-optional-pymupdf.md). Historical issue
#1950 described the intent; issue #3159 implements this concrete boundary.
A separate plugin contract is outside this change.

## LICENSE-02 — psycopg / psycopg-binary / psycopg2-binary (LGPL)

**Status: resolved via disclosure, low severity, no migration in scope.**

`psycopg2-binary` (LGPL-2.0-only) and `psycopg`/`psycopg[binary]` v3
(LGPL-3.0-only — psycopg3 did not drop the LGPL) are the PostgreSQL drivers
used by `fred-core` and `knowledge-flow-backend`. Verified from PyPI wheel
metadata.

Why this is low severity: both are used as **unmodified, dynamically
imported** packages — the standard LGPL linking-exception bar (don't modify
the library, let the user replace it, disclose the license) is met by normal
Python packaging. No static linking, no embedding, no combination into a
single non-separable binary.

Remediation: none required. The [README Licensing Note](../../README.md) was
corrected to disclose this instead of claiming a zero-copyleft dependency
tree. If a future deployment genuinely requires a zero-copyleft dependency
tree, the only clean alternative is swapping to a non-copyleft driver (e.g.
`asyncpg`, Apache-2.0) — a real migration (different API, sync/async
semantics), not attempted, not currently justified by the low severity.

## LICENSE-03 — jwcrypto (LGPL-3.0-or-later)

**Status: disclosed, low severity, compliant as-is. Full removal of the
transitive dependency is tracked separately and not implemented.**

### Why it's here

Fred's own code never imports `jwcrypto`, and never even imports
`KeycloakOpenID` (the class in `python-keycloak` that handles JWT/JWK). Fred's
own token verification path — the security-critical one, for every incoming
request — is [`fred_core/security/oidc.py`](../../libs/fred-core/fred_core/security/oidc.py),
which uses `PyJWT` (MIT), not `jwcrypto`.

`jwcrypto` arrives purely as a **transitive** dependency of `python-keycloak`.
Fred's code only uses `python-keycloak`'s `KeycloakAdmin` class, for Keycloak
admin-API user-directory operations (create/list/delete users) in 4 files:
`keycloack_admin_client.py`, `users/service.py`, `users/dependencies.py`
(`control-plane-backend`), `users_service.py`
(`knowledge-flow-backend`). AUTHZ-05 removed the last group-membership calls
(`teams/service.py`/`teams/dependencies.py` no longer touch `KeycloakAdmin` at
all — team membership is OpenFGA-only). But `python-keycloak`'s `keycloak_admin.py` module
imports `openid_connection.py`, which imports `keycloak_openid.py`, which does
`from jwcrypto import jwk, jwt` unconditionally at module load time — so the
import happens as soon as `KeycloakAdmin` is used, even though nothing in Fred
calls the JWT-decoding functionality that actually needs `jwcrypto`.

Confirmed by inspecting every `uv.lock` in the monorepo (`fred-core`,
`control-plane-backend`, `knowledge-flow-backend`, `fred-agents`, `fred-sdk`,
`fred-runtime`): **`python-keycloak` is the sole source of `jwcrypto`** across
the entire dependency tree. Version at time of writing: `jwcrypto==1.5.7`
(via `python-keycloak==7.1.1`).

### Why it's low severity

Same LGPL linking-exception analysis as `LICENSE-02`: unmodified pip package,
dynamically imported, not statically linked or embedded, replaceable by the
end user via normal Python packaging. This holds regardless of whether the
JWT-decoding code path is ever exercised — the fact that it currently isn't
reduces practical exposure further, but is not itself the compliance
mechanism.

### Current mitigation: disclosure

Disclosed in this document's `LICENSE-03` entry above and the README Licensing
Note, alongside `LICENSE-01`/`02`.
No code change involved, and none required — this is the same LGPL
linking-exception bar `LICENSE-02` already clears: unmodified, dynamically
imported, replaceable, disclosed.

### Full removal (not implemented)

For teams that want to state "zero copyleft dependencies" without any
caveat, the only way to get there for `jwcrypto` is to remove
`python-keycloak` entirely and replace `KeycloakAdmin` with direct calls to
Keycloak's Admin REST API via `httpx` (already a Fred dependency), including
the client-credentials token acquisition
(`POST /realms/{realm}/protocol/openid-connect/token`).

Scope is bounded: only **4 distinct `KeycloakAdmin` methods** are called
anywhere in the codebase — `a_get_user(s)`, `a_create_user`, `a_delete_user`
— each a well-documented standard Keycloak Admin REST endpoint. This is a
mechanical port (one REST call per existing method call, no business-logic
change) across the 4 files listed above, but it does touch production
security-path code, so it is tracked as its own item rather than bundled into
this disclosure change.

Tracked in: **GitHub issue [#1949](https://github.com/ThalesGroup/fred/issues/1949)**
— no RFC planned, since this is a like-for-like dependency substitution with
no design decision to make; flag here if that turns out not to hold once
someone starts the port.
