# Design

Only decisions already taken. Anything still open lives in the RFC, not here.

## Lockstep versioning for the three libraries

`fred-core`, `fred-sdk` and `fred-runtime` carry one version number and move
together. Independent versioning is what produced seven consumers on seven
different floors with no way to tell which combinations were ever tested.

The cost is real and accepted: a bump in one library forces a bump in all three,
so some releases carry no change for two of them.

## `runtime_id` is a bare slug

It names a **deployed service**, not a publishable artifact, so it only has to be
unique within one installation. Kubernetes spells the same distinction: an API
group is domain-qualified (`widgets.example.com`), a Service is a short slug.
OpenTelemetry agrees — `service.name` is a plain slug and is explicitly not
required to be globally unique.

The practical constraint decided it: `runtime_id` becomes the `service` KPI
dimension, and the other backends already publish bare slugs there
(`control-plane`, `knowledge-flow`, `rags-services`). A domain-qualified pod
would be the only irregular value inside the same label.

At scale, scope goes in a **separate dimension** — never in a longer name.
`PROMETHEUS_ALLOWED_LABELS` already carries `env` and `cluster`.

## `runtime_id` must match the control-plane catalog

The pod names itself in its own `configuration.yaml`; the control-plane lists it
under `runtime_catalog_sources`. Both sides must carry the same string — that
equality is what joins a log line to its own KPI.

Nothing validates the two sides agree. A typo yields an orphan telemetry identity
with everything green. Noted, not solved here.

## Identity belongs on the catalog entry, not in a parsed id

`CapabilityCatalogEntry` is already the one model behind all five kinds
(`tool | agent | model | app | knowledge_base`). The unification the UI needs
exists; what is missing is honest identity on it.

Two defects, both in the contract rather than the frontend:

**Provenance is implicit.** The entry's `id` is a composite of `runtime_id` and
`agent_id`, mangled to be colon-free because OpenFGA rejects `:` in object ids,
and documented as "used ONLY for ReBAC checks and the admin catalog". The pod
knows both values and sends neither as a field. Making the frontend
reverse-engineer that encoding would couple it to a ReBAC storage detail, so
instead the entry gains `runtime_id` (which pod advertises it, `None` for kinds
that are not pod-hosted) and `source_id` (the identifier its author wrote, e.g.
`fred.samples.assistant`).

**`version` is real for some kinds and invented for others.** The field carries a
genuine artifact version where one exists: the five shipped capabilities all
declare `0.1.0`, semver, matching their package. Applications populate it from
their own version. But the agent and model projections stamp a literal —
`version="1"` at `product/service.py:775` and `:875` — because agents have no
version concept yet, and two capability sites use `"0"`.

So the field is sound and the projections abuse it. The fix is not to rename it:
`version` becomes **optional**, agents and models stop inventing a value, and the
UI shows a version only where one truly exists. A false `v1` on every agent is
worse than no version at all, because it looks like information.

(The field also doubles as the stored-config `schema_version` on the save
round-trip — one field with two jobs. Noted, not addressed here.)

## Local override, not a fork

Each satellite resolves `fred-*` from the monorepo checkout through
`[tool.uv.sources]`. The published floor stays declared in `dependencies`;
commenting one line out restores PyPI resolution. This is a development-time
override so a library change is testable before it is published — it is not a
fork, and the satellites still depend only on published libraries.
