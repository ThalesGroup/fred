## 1. Service resolution

- [x] 1.1 Add the SDK service-address contract and catalog references; verify custom prefixes/ports, inprocess behavior and invalid reference rejection with SDK tests.
- [x] 1.2 Implement the runtime config adapter and inject it into packaged/external catalog loading; verify configured/missing services, provider failures and override precedence.
- [x] 1.3 Replace internal literal URLs in the package and Helm defaults; verify installed package boot, chart configuration and SDK-only wheel loading; remove redundant internal YAML port rewriting.

## 2. Integration and close-out

- [x] 2.1 Update package/app README, authoring guide and skill, runtime contract and existing migration note; verify examples match the implementation.
- [x] 2.2 Run affected test suites, root code-quality and independent standards/spec reviews; fix findings and record results here.
- [x] 2.3 Reconcile and archive the OpenSpec change; verify spec validation and confirm all work remains uncommitted.

Verification (2026-09-29):
- Root `make code-quality`: all modules passed. Package-specific Ruff and format
  checks, app lock validation and `git diff --check` passed.
- Full `make test`: SDK 540 passed / 3 skipped; runtime 1647 passed / 11 skipped
  (optional fastapi_mcp absent) / 17 deselected; agents 91 passed / 6 existing xfails.
- Final focused tests after review fixes: SDK catalog/capability 55 passed;
  runtime service/catalog/config 49 passed; agent team-scope guard 1 passed.
- Raw basedpyright: SDK and agents zero errors/warnings; runtime zero errors and
  seven existing unreachable-code warnings.
- Clean-source wheel loaded using SDK only with runtime imports forbidden: all
  eight resolved servers equal the original default catalog; internal YAML has six
  service references and no URL literals. Installed boot exercises a custom
  HTTPS address, port 9443 and API prefix.
- Chart schema regenerated (unchanged); values validation and migration-check pass.
  Independent review loaded rendered Helm defaults and confirmed original resolved
  server configurations/instructions, plus custom-address propagation.
- Independent spec review: no findings. Standards review: empty query/fragment
  delimiters could corrupt joined paths; fixed for base URLs and paths with regression
  tests. Follow-up review confirmed no remaining findings.
- No Docker build or live MCP connection test; resolution itself performs no I/O
  beyond existing startup catalog/instruction reads.
