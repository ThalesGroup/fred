## 1. Prompt behavior

- [x] 1.1 Update the packaged tabular prompt to answer first, offer a chart only when helpful, and call `chart_render` only after an explicit request or opt-in; verify the prompt diff against all three spec scenarios.

## 2. Contract and verification

- [x] 2.1 Validate the OpenSpec delta, sync the changed requirement into the durable spec, and verify the three scenarios are present.
- [x] 2.2 Review the branch diff against its geo base, check for other automatic chart instructions, and run `git diff --check`.
