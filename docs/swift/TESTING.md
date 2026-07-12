# How do you test it?

You have internet, a Unix laptop, and you're curious whether this checkout of
Fred actually works. Here is exactly what to do — four steps, each one ending
with a short, honest answer to "did that work?" that doesn't bury you in
detail.

This checks one specific axis end-to-end: **identity and authorization**
(Keycloak authenticates, OpenFGA decides who can do what — see
[`platform/REBAC.md`](platform/REBAC.md)). It is not a
full product test suite — there isn't one today. Treat a clean run through
all four steps as "this checkout is a sound release candidate on the axis
that matters most for a multi-tenant platform: nobody sees or touches what
they shouldn't."

## 0. Clone `fred`, run the offline tests

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
make test
```

**✅ What tells you this worked:** the command only reaches the end if every
submodule's suite passed (`make test` stops on the first failure). It
finishes with a coverage table, one line per submodule — that table is the
report, nothing else to run. Real example from a clean run:

```
  ── Coverage summary ───────────────────────────────────────────
  libs/fred-core                              84%
  libs/fred-sdk                               78%
  libs/fred-runtime                           72%
  apps/fred-agents                            60%
  apps/control-plane-backend                  83%
  apps/knowledge-flow-backend                 n/a
  apps/frontend                               13%
  ───────────────────────────────────────────────────────────────
```

`knowledge-flow-backend` showing `n/a` is a known reporting gap (its tests
still ran and passed — the summary just can't find its coverage file) —
not a sign anything failed. `apps/frontend` at 13% looks alarming next to
the Python submodules but reflects real current coverage practice on that
project, not a step-0 problem.

## 1. Clone `fred-deployment-factory`, start the backing services

```bash
git clone https://github.com/fred-agent/fred-deployment-factory.git
cd fred-deployment-factory
```

The default branch is `swift` — you don't need to check it out explicitly.

First-time-only setup:

```bash
docker network create fred-shared-network --driver bridge
cp docker-compose/.env.template docker-compose/.env
```

Then:

```bash
make docker-wipe    # only if a previous stack is already running
make docker-up
```

This starts Keycloak, Postgres, OpenFGA, OpenSearch, Temporal, and the other
backing services — **not** the three Fred applications themselves, that's
step 2.

**✅ What tells you this worked:** `docker-up` runs its own preflight and
prints a readiness verdict at the end — this *is* the report, no extra
command needed:

```
Readiness:
✓ GREEN: ready to start FRED (no critical/warning issues detected).
• Critical issues: 0
• Warning issues: 0
```

Anything other than `GREEN` with `0`/`0` means stop here and fix that first —
steps 2 and 3 will not give you a trustworthy answer on top of a broken seed.

## 2. Start the Fred components, pointed at the real backing services

Three API components are always needed. A fourth — the knowledge-flow
**worker** — is a separate process and easy to forget: skip it and
`validation-report` still passes (it doesn't ingest anything), but the moment
you try to upload/ingest a document from the UI, it will hang or fail with no
obvious cause. **If your manual pass touches documents at all, start it.**

Back in your `fred` checkout, each app needs a local `.env` copied from its
template:

```bash
cp apps/control-plane-backend/config/.env.template apps/control-plane-backend/config/.env
cp apps/fred-agents/config/.env.template apps/fred-agents/config/.env
cp apps/knowledge-flow-backend/config/.env.template apps/knowledge-flow-backend/config/.env
```

Open each of the three `.env` files and check `CONFIG_FILE`: it must point at
`configuration_prod.yaml`, not `configuration.yaml` — that's the profile
wired to real Keycloak/OpenFGA/Postgres/OpenSearch instead of local
stand-ins. `control-plane-backend` and `fred-agents` already default to it;
**`knowledge-flow-backend`'s template does not** — change that one line by
hand:

```
CONFIG_FILE="./config/configuration_prod.yaml"
```

Every secret placeholder left blank in the three `.env` files (Keycloak
client secrets, `OPENFGA_API_TOKEN`, Postgres/OpenSearch/MinIO passwords) is
the same fixed local value `fred-deployment-factory` seeds everywhere in this
setup: `Azerty123_`. Fill each one in with that.

Then, in three separate terminals, from the `fred` repo root:

```bash
make run-control-plane
make run-fred-agents
make run-knowledge-flow
```

**✅ What tells you this worked:**

```bash
curl http://localhost:8222/control-plane/v1/healthz
curl http://localhost:8111/healthz
```

Both should answer. `fred-agents` (port 8000) has no dedicated health
endpoint today — the only signal right now is its own terminal showing
`Uvicorn running on http://0.0.0.0:8000` without an error. That asymmetry is
a real gap, not something this guide is glossing over — worth closing later,
not blocking today.

### 2.bis — the knowledge-flow ingestion worker (only if you're testing documents)

This is **not** one of the three API components above — it's a separate
Temporal worker process, using yet another config profile
(`configuration_worker.yaml`, not `configuration_prod.yaml` — the Makefile
target sets it for you, no `.env` edit needed beyond what you already did).
It needs Temporal, which is already part of the step-1 backing services.

In a fourth terminal:

```bash
cd apps/knowledge-flow-backend
make run-worker
```

First run downloads local ML models, so it's slower to start than the three
API components — that's expected, not a hang.

**✅ What tells you this worked:** there's no `/healthz` for a worker (it has
no HTTP server) — the signal is the terminal log reaching a "waiting for
tasks" / workflow-registration line without an error, and, in practice,
that a document you upload from the UI actually finishes ingesting instead
of sitting at "processing" forever.

The control-plane backend has its own analogous worker
(`cd apps/control-plane-backend && make run-worker-prod`, also Temporal —
handles deferred erasure/purge-queue reconciliation, see `CTRLP-12`). Not
required for the steps below; noted here because we'll want to test it too
— see `NOTES-AUTHZ05-REVIEW.md`'s "À suivre" section.

## 3. Run the authorization validation suite

```bash
cd fred-deployment-factory
make validation-report
```

**✅ What tells you this worked:** `validation/report.md`, and specifically
its first two lines — everything below them is detail you only need when
something is red:

```
**Result:** READY - no unexplained findings
**Totals:** 215 passed, 0 failed, 0 error, 0 known gap (xfail), 0 possible infra issue, 0 skipped
```

`READY` at the top means: every seeded identity (platform admin, platform
observer, team admins/editors/members, identity-only users) sees exactly
what they should and nothing else, proven live against the real running
stack — not asserted, not assumed.

---

If all four steps end green, you have a working, authorization-sound release
candidate. If step 3 is red, `report.md` groups every failure by the
real-world claim it breaks (not by test function name) — read that table
next, not the raw pytest output.

## What this doesn't cover: the UI itself

Everything above proves the API. It says nothing about whether the browser
actually hides a button it should, or shows a sane error. That layer is:

- **`/admin/self-test`**, as a real `platform_admin` in the browser — a
  functional self-test (real documents, real agent turns) and an
  authorization self-test (proves the API/UI honor the model for your own
  session, or for any other account you have the password for). See
  [`platform/FRONTEND-AUTHZ-PATTERN.md`](platform/FRONTEND-AUTHZ-PATTERN.md)'s
  testing pyramid for exactly which layer proves what.
- The manual, multi-persona checklist for anything neither of the above
  reaches. See [`../../NOTES-AUTHZ05-REVIEW.md`](../../NOTES-AUTHZ05-REVIEW.md)
  for the current state of that campaign.
