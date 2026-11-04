## 1. Invocation and coverage

- [x] 1.1 Set packaged `grounded-research` to `user-invocable: false`; extend existing model-only eligibility coverage and verify user catalog exclusion, direct-selection rejection, autonomous access and global disablement.
- [x] 1.2 Extend existing instruction-delivery coverage for autonomous ReAct, native Deep parent and child loads; verify complete research instructions and agent-origin attribution with no user selection.

## 2. Verification and close-out

- [x] 2.1 Update `docs/swift/ops/migrations/platform-skills-evolution.md` for four model-only skills and the runtime rollout; verify it agrees with the proposed matrix and stale-selection behavior.
- [x] 2.2 Run focused runtime skill tests and obtain author/independent contract review; record results below. Stop the root quality run and all further verification as explicitly requested by the developer before pushing.
- [x] 2.3 Reconcile the implementation, validate and sync the capability matrix, archive the change and commit the completed block for delivery through the authorized PR workflow, with #3402 retained as tracking.

Evidence: 139 focused runtime tests passed after rebasing onto
`f2e5bc09c79ac6dd612dfcfb27f89477cfcef2ee` (14.50 seconds, one existing
LangChain beta warning). Raw runtime typing reported 0 errors and 7 existing
unreachable-code warnings. Migration declaration and strict change validation
passed; all 38 current specs validated and the synced requirement matched the
approved delta with existing scenarios preserved.

Independent read-only review covered base `f2e5bc09c` through implementation
head `b322cd148`, with no actionable findings. Author review also covered the
final main-spec synchronization. Parent PR #3342, live browser/provider behavior
and deployed multi-replica execution were excluded. The metadata change adds no
queries, requests or shared state.

The developer explicitly requested "Push mtn stop lesvérification". Root
`make code-quality` was interrupted accordingly and is not claimed as passing.
No further verification was run after that instruction. The missing gh-stack
extension is handled by delivering a conventional dependent draft PR.
