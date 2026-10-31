---
name: quality-root
description: Run the full monorepo code-quality target when the user requests root-wide validation. Ordinary increments follow the affected-component scope in AGENTS.md.
---

# Root code quality

Read the active checkout's `AGENTS.md` and root Makefile, including the actual
module list and included targets. Do not copy a historical list of components.
An explicit request for this skill authorizes `make code-quality` from that root.
For routine implementation, use the affected-component checks required by
`AGENTS.md`; this skill does not make every change a root-wide campaign.

Run the target with sufficient time for cold dependency setup. Inspect each
module's exit status and diagnostics, including formatter warnings. A module
not reached after an earlier failure is unverified, not passing. Do not bypass
checks, refresh baselines or weaken typing just to obtain success.

If fixes are requested, correct the root cause within scope and rerun the affected
checks. Preserve unrelated work. Report modules checked, actual failures and
remaining blockers concisely. Tests, benchmarks and deployment are separate work;
do not run them implicitly.
