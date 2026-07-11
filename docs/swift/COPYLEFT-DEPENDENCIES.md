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

Tracked centrally under the `LICENSE` domain in
[`id-legend.yaml`](data/id-legend.yaml); originated from GitHub issue
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
| `LICENSE-01` | `pymupdf`, `pymupdf4llm` | AGPL-3.0 (dual, Artifex commercial alt.) | `knowledge-flow-backend` PDF pipeline (primary extractor in 3 of 4 usage sites) | **High** | Decided: make optional, non-AGPL default path. Tracked in issue #1950, milestone `swift-golive`. Further plugin separation deferred to `INGEST-01` |
| `LICENSE-02` | `psycopg`, `psycopg[binary]`, `psycopg2-binary` | LGPL-3.0-only / LGPL-2.0-only | `fred-core`, `knowledge-flow-backend` (Postgres driver) | Low | Resolved via disclosure — no code change needed |
| `LICENSE-03` | `jwcrypto` | LGPL-3.0-or-later | Transitive, via `python-keycloak`'s `KeycloakAdmin` — `fred-core`, `control-plane-backend`, `knowledge-flow-backend`, `fred-agents`, `fred-sdk`, `fred-runtime` | Low | Disclosed, compliant as unmodified/dynamically-imported dependency. Full removal of the transitive dependency tracked separately (issue #1949), not implemented |

---

## LICENSE-01 — pymupdf / pymupdf4llm (AGPL-3.0)

**Status: high severity. Decision made — make the dependency optional with a
non-AGPL default path (tracked in issue [#1950](https://github.com/ThalesGroup/fred/issues/1950),
milestone `swift-golive`). Not yet implemented.**

Dual-licensed AGPL-3.0 / Artifex Commercial License (verified from PyPI wheel
metadata). Today `pymupdf`/`pymupdf4llm` are **mandatory** dependencies of
`knowledge-flow-backend` (`[project.dependencies]`, not
`[project.optional-dependencies]`) — every default build/image contains this
AGPL code regardless of any config value. Three sites import them
unconditionally at module load, with no fallback: the "lite" fast-path PDF
pipeline (`lite_pdf_to_md_processor.py`, `lite2_pdf_to_md_processor.py`,
wired in every config profile with no extractor switch) and the PPTX
slide-rendering path (`pptx_slide_renderer.py`). It is actively invoked in
production. The main pipeline (`pdf_markdown_processor.py`) already defaults
to the MIT-licensed `docling` extractor in nearly every config profile (one
remaining profile in `configuration_postgres.yaml` still selects `pymupdf`
explicitly), with a code-level fallback that itself still defaults to
`pymupdf` when the config value is missing/unrecognized.

Why this is more serious than the others in this document: AGPL's
network-use clause can require source disclosure for a networked service that
runs (even unmodified) AGPL code, and Fred is a networked service. "It's
rarely invoked" is not available as a defense here — the code path is
genuinely exercised on every PDF ingested.

### Decision — Option 1: optional dependency, non-AGPL default path

Move `pymupdf`/`pymupdf4llm` into an optional dependency group, fix the three
unconditional-import sites to default to `docling`/`pypdf` (already
dependencies), flip the `pdf_markdown_processor.py` fallback default away
from `pymupdf`, and ensure the default build/image never installs the
optional extra. Result: Fred as built and distributed by default contains no
AGPL code; a deployer who wants pymupdf's speed/quality installs the extra
and opts in via config explicitly, at which point the AGPL/Artifex
implications for that deployment are theirs to manage. Tracked end-to-end in
issue #1950.

### Deferred — full plugin separation

Going further — shipping the pymupdf-touching processors as a fully separate,
out-of-tree installable plugin package, so the code isn't even in this repo
— requires a real plugin/extension contract. That contract is what
`INGEST-01` ([`EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md`](rfc/EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md),
currently draft, status `not_started`) is designing; today's `class_path`/
`suffix` YAML mapping is only a "proto-plugin system" per that RFC's own gap
analysis. No bespoke plugin mechanism is being built for pymupdf alone — this
follow-up rides on `INGEST-01` once it is confirmed and implemented, expected
no earlier than the `swift ga` milestone (2026-09-30).

An Artifex commercial license remains a fallback option if the migration to
`docling`/`pypdf` turns out to regress extraction quality unacceptably — not
pursued unless that happens.

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
admin-API operations (create/list/delete users, list/manage group membership)
in 7 files: `keycloack_admin_client.py`, `teams/service.py`,
`teams/dependencies.py`, `users/service.py`, `users/dependencies.py`
(`control-plane-backend`), `keycloak_rebac_sync.py`, `users_service.py`
(`knowledge-flow-backend`). But `python-keycloak`'s `keycloak_admin.py` module
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

Disclosed in this document, the [`id-legend.yaml`](data/id-legend.yaml)
`LICENSE-03` entry, and the README Licensing Note, alongside `LICENSE-01`/`02`.
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

Scope is bounded: only **9 distinct `KeycloakAdmin` methods** are called
anywhere in the codebase — `a_get_user(s)`, `a_create_user`, `a_delete_user`,
`a_get_group(s)`, `a_get_group_members`, `a_group_user_add`,
`a_group_user_remove` — each a well-documented standard Keycloak Admin REST
endpoint. This is a mechanical port (one REST call per existing method call,
no business-logic change) across the 7 files listed above, but it does touch
production security-path code, so it is tracked as its own item rather than
bundled into this disclosure change.

Tracked in: **GitHub issue [#1949](https://github.com/ThalesGroup/fred/issues/1949)**
— no RFC planned, since this is a like-for-like dependency substitution with
no design decision to make; flag here if that turns out not to hold once
someone starts the port.
