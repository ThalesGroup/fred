## Context

See proposal.md — Why.

The shared library already owns every type involved: the security configuration
and its user, workload, delegation and authorization blocks; the grant parameter
names; the asserted principal; and the request-principal resolution that reads a
grant. What it does not own is the assembly. It offers one way to load a
configuration, from a file, which the platform backends use and installed
applications do not.

The tool-server package rebuilds an inner request from the declared arguments of
the tool being called. A grant presented on the outer endpoint is therefore
visible to the mount and absent from the route the tool resolves to, which is
why a bridge exists at all.

## Goals / Non-Goals

Goals:

- One implementation of the grant's journey across a tool mount, and one of the
  security assembly, used by the platform backend and every installed
  application.
- No new required dependency for the shared library.
- No deployment change: variable names and meanings are preserved.

Non-Goals:

- Application domain logic stays in the application. A review's lease, claim and
  stage ordering look like infrastructure and are not.
- Datastore client construction stays in the application: indices and
  credentials are genuinely per-application.
- Small environment helpers stay where they are. Unifying a four-line reader
  would create a shared interface for something with no shared meaning.

## Decisions

**The surface lives in the shared library, not in a module shared between
applications.** The library already owns every type being assembled, and a
platform backend needs the same bridge, which a module shared only between
applications could not serve. Alternative considered: a shared module inside the
applications repository. Rejected — it serves only half the callers and removes
the self-containment that lets one application be read on its own.

**The tool-server dependency is optional.** Only the subclass that injects the
grant into an inner call needs it. The library is consumed by services that
mount no tools, so it gains an optional extra rather than a required dependency,
and an import without it fails naming the extra. Alternative considered: ship
only the injection function and leave a small subclass in each application. Kept
as a fallback — it still moves every security-relevant line, at the cost of a
few lines of wiring per caller.

**Removing the grant parameters from model-facing schemas needs no dependency.**
It reads a tool's schema structurally, so it is typed on a protocol rather than
on the tool-server's own class.

**A grant is read from the endpoint only.** The two existing copies disagree:
one confines the grant to the endpoint, the other also reads the enclosing body.
The endpoint-only rule is adopted because the body of a tool mount is the tool
call, which the calling model influences. Alternative considered: accept either
transport. Rejected — it lets a caller name a person through content it partly
controls, and the library already refuses to merge a grant across two
transports.

**The mount requires a bearer explicitly.** The bearer scheme does not fail on a
missing credential, so without an explicit refusal an unauthenticated request
reaches token decoding as an empty value and depends on that failing. Neither
existing copy does this; the shared one does.

**The delegation block travels as one structured value.** A variable per field
would make every new field in that block a code change in every application.

## Risks / Trade-offs

**The shared library is consumed by the platform backends, so a defect here
reaches further than the applications.** → The behaviour moved is already
covered by the platform backend's tests; those move with it and run against the
shared implementation before any application adopts it.

**Unifying the mount changes behaviour for the existing callers, in opposite
directions: one gains an explicit bearer refusal, the other stops reading a
grant from the body.** → Both are tightenings, and each is pinned by a scenario
in the spec. A deployment relying on a grant in the body would break; no
deployment does, because the runtime places the grant on the endpoint.

**An optional extra can be absent at runtime and fail late.** → The import
raises naming the extra, and the applications that need it already pin the same
tool-server version.

**Moving security code creates a window where two implementations exist.** →
Callers migrate within this change, and the local copies are deleted rather than
left to drift.

## Migration Plan

1. Land the shared modules with their tests, exported from the package root.
2. Move the platform backend to the shared bridge, keeping its mount path and
   tags. Its existing tests are the regression gate.
3. Move each installed application to the shared assembly and bridge, deleting
   the local copies.
4. Applications that mount tools without a bridge adopt it, gaining delegated
   behaviour that fails closed today.

Rollback: the shared modules are additive, so a caller can be reverted to its
local copy independently. Nothing in a deployment changes, so no rollback step
touches configuration.

## Open Questions

- Whether a variant that requires the grant parameters, rather than accepting
  them as optional, is needed for routes that may only ever be reached by a
  delegated caller. It can be added later without changing the behaviour
  specified here.
