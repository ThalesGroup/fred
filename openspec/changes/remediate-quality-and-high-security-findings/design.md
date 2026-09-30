## Context

See proposal.md. The default branch has 1 reliability error, 7 reliability notes, and 153 maintainability notes in GitHub Code Quality. Most notes are intentional `await`/Protocol/Alembic/import patterns; changing them blindly could damage behavior. The GitLab screenshots show High findings in a frontend lockfile, tabular SQL, and frontend fetches, but do not contain the complete report or taint traces.

The control plane already describes execution endpoints as ingress-relative, yet `RuntimeCatalogSourceConfig.ingress_prefix` is an unrestricted string. The frontend passes the resulting `execute_stream_url` to bearer-authenticated `fetch` calls. The tabular service validates one SELECT and authorized relation aliases, then executes agent-supplied SQL on a DuckDB connection in a worker thread. Selected Parquet artifacts may be local or reachable through short-lived internal signed URLs.

## Goals / Non-Goals

**Goals:**

- Keep the existing execution and tabular APIs while enforcing their documented trust boundaries.
- Preserve authorized analytical queries and bounded execution; make rejection of unsafe inputs explicit and testable.
- Reach Excellent Code Quality ratings by fixing real defects and triaging intentional findings with traceable reasons.

**Non-Goals:**

- Change the agent's SQL authoring interface or the source of tabular authorization.
- Replace Code Quality or GitLab scanning with local heuristics.

## Decisions

### Validate execution URLs at both ends of the preparation contract

Add one backend validator for canonical root-relative `ingress_prefix` values, then regenerate the published configuration schemas. The frontend uses one shared guard at every bearer-authenticated runtime fetch to reject absolute, network-path, encoded, or otherwise ambiguous endpoints before the request. Check the resolved origin as a final defense. This follows the existing documented relative-URL contract. Backend-only validation would not protect a compromised preparation response; frontend-only validation would let invalid configuration remain deployed. Update absolute-URL test fixtures to reflect the contract.

### Constrain agent SQL structurally and restrict DuckDB external access

Keep the single-SELECT and authorized-relation checks, and reject table-function sources and scalar functions that inspect process or DuckDB configuration. Derive pure built-in scalar and aggregate names once from the pinned DuckDB function metadata, rather than a hand-maintained list. Inspect native macro bodies transitively and reject any that read a relation or call a restricted function; this closes wrappers such as `pg_sleep` and `pg_get_viewdef`. Reject unknown names and direct configuration-inspection calls before execution. Mount only the selected authorized Parquet artifacts; configure DuckDB `allowed_paths` to those exact locations and disable other external access. A local probe confirmed that a view over an allowlisted Parquet file remains queryable while `/etc/passwd` is blocked. It also confirmed that `current_setting('allowed_paths')` exposes the allowlist, so expression validation is required to protect signed URLs. Preserve `httpfs` setup before locking access and verify local and signed-URL behavior in targeted tests.

Use the existing execution admission, cancellation, time, memory, and row limits. SQL string interpolation in internally generated queries remains limited to quoted identifiers/literals and bounded numeric values; add regression tests at the reported entry points. An isolated process would provide a stronger boundary but requires moving current thread-bound connection and cancellation orchestration plus signed-URL access across processes. Treat that as a separate architectural follow-up only if the constrained query design fails security validation; do not claim DuckDB settings alone form a complete sandbox.

### Triage scanner findings from the actual data flow

For each GitLab High finding, record the package identity or source-to-sink path and distinguish a fix from a false positive. The lockfile's `node_modules/canvas` entry resolves to the npm alias `@napi-rs/canvas@0.1.96`; the cited CVE concerns the different `canvas` package. Verify the complete dependency graph before any dependency change. Browser-side `fetch` calls to fixed same-origin paths are not server-side requests, but the preparation URL case still deserves the guard above. SQL findings that interpolate fixed migration constants or already quoted identifiers can be triaged after targeted tests. The complete GitLab export is needed to close this inventory.

For GitHub Code Quality, export finding numbers, rules, files, and current state. Fix the actionable reliability error/notes and maintainability notes in small reviewable groups. Preserve intentional lifecycle, migration, and registration semantics; dismiss or otherwise triage those findings with specific reasons through GitHub's finding controls. Recheck counts and ratings after the default-branch scan. The rating is an external result, so local tests alone cannot prove Excellent.

## Risks / Trade-offs

- [SQL compatibility] Pure built-in analytical functions remain available, while volatile functions such as random or sleep are rejected. A DuckDB upgrade can add a new sensitive scalar function -> review function metadata during upgrades and keep the configuration-inspection, relation, and external-access regression tests.
- [Remote dataset access] Disabling external access may interact with `httpfs` and signed URLs -> test both local and remote mounts before rollout; keep exact path grants rather than allowing an entire host or directory.
- [Configuration migration] Deployments using absolute runtime prefixes will fail validation -> document the required root-relative form and validate deployed values before upgrade.
- [Scanner rating] Some legitimate code patterns may remain open until GitHub finding triage or a fresh default-branch scan -> capture finding IDs and before/after counts in the PR, then complete the scanner workflow.
- [Report coverage] Screenshots omit High findings and taint traces -> reconcile the full GitLab export with the PR inventory before declaring all High findings resolved.

## Migration Plan

1. Validate runtime source prefixes in the active deployment configuration and convert any absolute values to ingress-relative paths.
2. Deploy control-plane and frontend changes together; the frontend guard safely fails if an older backend emits an invalid endpoint.
3. Verify local and remote tabular queries, then observe query rejection and timeout behavior after deployment.
4. After merge, rerun GitHub Code Quality and GitLab scans, triage confirmed false positives, and record the final ratings and High finding dispositions in the common PR and issue.
