# Independent review prompt

Replace checkout, commit and scope with verified current values. Keep the boundary
explicit; a future feature is not a review defect. Use this for a read-only review,
not as implicit permission to fix, deploy, reset or publish.

> Apply `$fred-reconstruction-method` and the repository's `audit-control-plane`
> procedure to this checkout: [absolute checkout], baseline [commit]. Record HEAD
> and any local changes; do not assume that the baseline is deployed or validated.
>
> Review the complete agreed journey [start -> end], not just the last diff.
> Start with the arc42 question map and code source map, then independently trace
> the actual UI, API, authorization, persistence and configuration. Preserve existing
> Fred semantics and all supported identity modes; identify approved changes separately.
>
> I want a limited scope with complete, simple and defensible behavior. Look for
> missing prerequisites, security regressions, unjustified complexity, duplicated
> configuration, implementation/documentation disagreements and exposed incomplete
> paths. Do not demand future features or invent their UI. A successful build or a
> test name is not proof that a user journey works.
>
> Check that each arc42 section answers its own reader question at the proper
> level. A system overview is not a deployment inventory. Unagreed sections must
> remain empty; request editorial agreement before filling or substantially
> rewriting them. Do not award completeness for generic filler.
> Apply the mandatory fred-architecture skill: main chapters explain current Fred
> for architects, clients and security readers. Keep SQL inventories and all source
> references in technical annexes, with useful links to the human explanations.
> Keep proposed features and open design choices outside arc42.
> Identify relevant old RFC/OpenSpec content to reconcile
> into the canonical corpus; do not delete anything during this review.
>
> Return findings by severity with exact file/symbol or line, concrete trigger,
> violated contract, effect, minimal correction and regression scenario. Separate
> confirmed defects, documentation discrepancies, unresolved decisions and unverified
> claims. Provide coverage and exclusions, including consumer/dependency boundaries.
> State what you actually checked; do not claim full product readiness.
>
> Work independently and read-only. Do not change files, stage, commit, push, deploy
> or mutate the running environment. Respect the current permission for tests;
> missing verification remains visible. Do not recursively delegate merely to claim
> independence. The implementation author will disposition findings and arrange
> focused correction/re-review rather than starting another unrelated audit.
