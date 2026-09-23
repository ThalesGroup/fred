## 1. Shared configuration surface

- [x] 1.1 Build a first-party application's security configuration from the
      environment in the shared library, taking only the caller's own workload
      secret and authorization token variable names; verify two callers
      differing only in those names receive the same profile and authorization
      mode.
- [x] 1.2 Read the delegation block from one structured value, defaulting to
      disabled when absent; verify a missing value disables delegation and
      trusts no caller.
- [x] 1.3 Refuse a malformed delegation value at startup rather than falling
      back to disabled; verify each unreadable shape raises and that an enabled
      block naming no caller is refused.
- [x] 1.4 Allow the workload issuer to differ from the person's, defaulting to
      the person's when unset; verify both cases, and verify the receiver
      audience falls back to the application's own workload identity.
- [x] 1.5 Export the builder from the package root; verify it imports from the
      root without reaching into a submodule path.

## 2. Shared MCP delegation bridge

- [x] 2.1 Provide mount authentication that refuses a request carrying no
      bearer; verify a request presenting any other credential and no bearer is
      refused and invokes no tool.
- [x] 2.2 Read the grant from the request endpoint only, never the enclosing
      tool-call body; verify a grant on the endpoint is honoured and one in the
      body leaves the call acting for nobody.
- [x] 2.3 Record the verified grant for the duration of the mounted call and
      release it afterwards; verify concurrent calls do not observe each other's
      grant.
- [x] 2.4 Inject the verified grant into the inner route call, discarding any
      grant arriving as a tool argument first; verify a forged argument is
      replaced by the verified grant, and that an undelegated call injects
      nothing.
- [x] 2.5 Remove the grant parameters from model-facing tool schemas while the
      routes continue to declare them; verify the parameters are absent from an
      offered schema and present on the route.
- [x] 2.6 Expose the grant parameters as an optional route dependency so a route
      declares them once; verify a route carrying it accepts the parameters and
      that its behaviour is unchanged without them.
- [x] 2.7 Keep the tool-server dependency optional, raising on import and naming
      the extra when it is absent; verify the schema-stripping helper works
      without that dependency installed.

## 3. Platform backend adoption

- [x] 3.1 Replace the platform backend's local delegation module with the shared
      one, preserving its mount path and tags; verify its existing delegation
      and MCP tests pass unchanged against the shared implementation.
- [x] 3.2 Remove the duplicate application of schema stripping the backend
      performs twice; verify the offered tool schemas are unchanged.

## 4. Installed application adoption

- [x] 4.1 Replace each installed application's hand-built security assembly with
      the shared builder, deleting the local one; verify each application starts
      with the same profile, authorization mode and delegation behaviour as
      before.
- [x] 4.2 Move the application that already carries a local bridge onto the
      shared one and delete the local module; verify its delegated tool calls
      still reach the route as the named person.
- [x] 4.3 Adopt the bridge in each application that mounts tools without one;
      verify a delegated tool call acts for the named person rather than for
      nobody.
- [x] 4.4 Give the applications that have no test suite one covering their
      security assembly; verify each fails when the hardened profile,
      authorization mode or delegation wiring is removed.

## 5. Verification

- [x] 5.1 Prove the endpoint-only rule end to end on a running deployment: a
      delegated tool call carrying its grant on the endpoint succeeds as the
      named person, and the same call carrying it in the body acts for nobody.
- [x] 5.2 Prove an application that previously mounted tools without a bridge
      serves a delegated tool call as the named person; record the audit events
      showing the grant accepted. Verified on a running deployment of the
      application: the tool call carrying its grant on the endpoint recorded the
      note as the named person and the stored record is attributed to an agent
      turn, the same tool call carrying the grant among its arguments instead
      was refused as acting for nobody, and the receiver emitted six
      grant-accepted audit events and no rejection. Corrected afterwards: that evidence
      used a tool whose route accepts a body, which carried the grant even
      though the application did not declare the grant parameters. A tool
      without a body had its grant dropped and reached the route acting for
      nobody. The application now declares the grant on every route, a test
      fails when that declaration is absent, and both a body-carrying and a
      body-less tool were re-verified on the deployment: the named person is
      served, a person outside the team is refused, and a call with no grant is
      refused.
- [x] 5.3 Confirm no deployment change was required: the same environment
      variables and structured delegation value drive every adopted caller.
