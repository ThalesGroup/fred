## Why

The default branch has a Poor GitHub Code Quality reliability rating and 161 open Standard quality findings. The current GitLab report also flags High dependency, SQL injection, and SSRF findings; these need evidence-based remediation so genuine defects are fixed and scanner false positives are correctly triaged.

## What Changes

- Resolve the open reliability and maintainability findings through focused source fixes or finding-specific triage, then verify the ratings on the default branch. The target is Excellent in both categories.
- Review every High finding in the complete GitLab report within the same issue and PR. Record the affected package or data flow, exploitability, disposition, and verification for each finding.
- Constrain browser-facing execution URLs to same-origin paths at configuration and consumption points so a runtime preparation response cannot redirect bearer-authenticated requests to another origin.
- Harden execution of agent-supplied tabular SQL while preserving authorized read-only queries over selected datasets. Verify that generated SQL continues to quote values and identifiers safely.
- Triage the frontend `canvas` dependency alert against the actual package resolved by npm and update dependencies only if the vulnerable package is present.

## Capabilities

### New Capabilities

- `runtime-execution-url-safety`: Browser-facing runtime execution URLs remain same-origin and cannot redirect bearer-authenticated requests.
- `tabular-query-safety`: Agent-supplied tabular queries execute only within an authorized, bounded read-only context.

### Modified Capabilities

None. The existing tabular-document-description requirements cover description reads, not agent-supplied query execution.

## Impact

- Tracking issue: #2871. One PR will cover the quality and High security findings.
- Likely code areas: `libs/fred-runtime`, `apps/control-plane-backend` configuration and execution preparation, `apps/frontend` execution fetches, `apps/knowledge-flow-backend` tabular query validation and execution, and affected tests.
- Configuration schemas, chart values documentation, and deployment guidance may change if invalid ingress prefixes are rejected.
- GitHub Code Quality and GitLab vulnerability triage are required to confirm the final ratings and finding dispositions. The screenshot is partial; the complete GitLab export is needed to certify coverage of every High finding.
