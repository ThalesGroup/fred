## 1. Common procedures

- [x] 1.1 Package adapted explicit-only grill-me with exact upstream revision and MIT license; verify distribution and representative invocation (#3304).
- [x] 1.2 Package analyze-data and agent-only data-visualization with available-tool limits and source/license provenance; verify positive/negative cases and compare representative outputs (#3305).
- [x] 1.3 Add frontend en/fr display metadata and verify eligibility/enablement behavior for new entries.

## 2. Integration

- [x] 2.1 Run packaged-resource and compiled-agent tests plus independent review; record quality-evidence limits, reconcile and archive.

Verification evidence (2026-10-27): seven new offline tests pass. Built wheel and
sdist contain all eight new resources; import/discovery/read works from the
extracted wheel outside the checkout. Distributed grill-me MIT license matches
upstream blob `f1dd2c09108dde1a5f56097cee8461b3ea834499` at source revision
`59db609eb1e18aaf59b63284d0e52255aff0c63c`; see its packaged NOTICE.md. Data
procedures are original Apache-2.0 text with primary methodological references.

Qualitative comparison: two fresh agents of the same model answered the same
five independent prompts with the same 130-word limit and text/arithmetic-only
capabilities. One received no procedures; one read the three skills/references.
This is one controlled qualitative sample, not a production model benchmark.

| Prompt | Without procedures | With procedures | Observed benefit or limit |
| --- | --- | --- | --- |
| Challenge a two-hour workshop for 30 volunteers | Identified decision authority, inclusion and agenda risks | Recommended three concrete choices, explained tradeoffs, then waited for answers | More actionable interview structure; both identified the core risks |
| 90/100 and 1/10 successes; causal improvement? | Correct 91/110 = 82.7%, rejected causal inference | Same correct result and caveat, plus table exposing both denominators | Clearer audit trail; no accuracy improvement on this simple case |
| Analyze an absent customer CSV | Asked for file, periods and metric | Asked for data, periods and absolute/percentage decline definition | Both avoided invented results; no demonstrated quality difference |
| Chart A=10, B=20 without a renderer | Returned truthful saveable SVG source, with proportional bars | Chose zero-based bars, supplied exact table, identified absent units/period, explained file limit | Stronger source/limit disclosure and supported fallback; did not produce a chart file |
| Translate a meeting time into French | Correct translation | Identical correct translation | No observed interference with the unrelated request |

Compiled fake-model comparisons separately prove instruction delivery before
inference and canonical input preservation; they do not measure answer quality.
