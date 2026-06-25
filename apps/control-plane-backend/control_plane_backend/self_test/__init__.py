"""Admin self-test harness (VALID-02).

A platform-admin-only, config-gated live-stack validation campaign. It seeds a
tiny deterministic golden corpus into a dedicated synthetic team, asserts on
retrieval, then deletes everything — validating the ingest -> index -> search ->
delete lifecycle against the real deployed stack.

See docs/swift/rfc/ADMIN-SELF-TEST-HARNESS-RFC.md.
"""
