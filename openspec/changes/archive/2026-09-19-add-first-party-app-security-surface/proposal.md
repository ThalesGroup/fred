## Why

A first-party application assembles the hardened security profile itself, from
environment variables, in roughly sixty lines that are identical in every
installed application. The delegated MCP path is duplicated the same way between
a platform backend and an installed application, and the two copies already
disagree on where a grant may travel: one confines it to the endpoint, the other
also accepts it from the enclosing tool-call body. Neither copy requires a bearer
explicitly, because the bearer scheme does not fail on its own.

The shared library owns every type these copies assemble and every rule they
enforce. It offers no way to build them, so each application re-derives security
behaviour that only one copy has tests for.

## What Changes

- The shared library builds a first-party application's `SecurityConfiguration`
  from the conventional environment. A caller supplies only the names that are
  genuinely its own — its workload secret and its authorization token — and
  receives the hardened profile, the user/workload issuer split, the optional
  receiver audience, reader-mode authorization and the delegation block.
- The delegation block is read from one structured value, so a new field in it
  is a deployment change rather than a code change in every application.
- The shared library provides the delegated MCP bridge: mount authentication
  that records the verified grant, injection of that grant into the inner route
  call, and removal of the grant parameters from model-facing tool schemas.
  Applications keep only their own mount path, tags and route declarations.
- A grant reaches a tool mount from the endpoint alone. The enclosing tool-call
  body is content the model influences, so a grant presented there is not read.
- A tool mount requires a bearer explicitly and refuses a request carrying none.
- A grant arriving as a tool argument is discarded before the verified grant is
  applied, so a model cannot name a person it was not delegated.
- The platform backend and every installed application that mounts tools adopt
  the shared bridge; those that mount tools without one gain delegated behaviour
  that fails closed today.

## Capabilities

### New Capabilities

- `first-party-app-security`: how the shared library configures a first-party
  application's security profile and carries a verified delegation grant across
  a tool mount into the route that serves it.

### Modified Capabilities

None. The grant contract, standing rules and receiver acceptance behaviour in
`delegated-execution-grant` and `delegation-subject-and-standing` are unchanged;
this change moves where that behaviour is implemented, not what it is.

## Impact

- Shared library: new configuration and MCP-delegation modules, exported from
  the package root. The MCP subclass depends on the tool-server package and is
  reachable through an optional extra so the library gains no required
  dependency.
- Platform backend: its local delegation module is replaced by the shared one,
  keeping its existing mount path and tags.
- Installed applications: each replaces its hand-built security assembly with a
  call, and those that mount tools adopt the bridge.
- Deployments: unchanged. The environment variables and the structured
  delegation value keep their current names and meanings.
