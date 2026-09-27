# Implementation slicing patterns

Pick the two or three that genuinely fit the spec. Name each option with the
real components (not "Option A"), draw it (timeline or dependency graph, same
axis across options), then list pros and cons *specific to this spec*. Generic
pros/cons below are prompts, not copy-paste material. End with a comparison
matrix and one recommendation.

## 1. Vertical slices (by end-to-end feature)

Each lot delivers one user-visible or test-visible path through every layer
(contract → backend → frontend/CLI). First slice is the thinnest possible.

- Pros: releasable and demoable after lot 1; integration risk surfaces early;
  feedback loop; each slice maps to one OpenSpec change cleanly.
- Cons: repeated touches on the same files across lots (merge friction);
  temporary scaffolding; harder when a shared foundation (schema, auth) must
  exist first.
- Fits when: the spec describes several independent flows; the team can ship
  behind a feature flag.

## 2. Horizontal phases (by layer)

Phase 1 contracts/types, phase 2 storage + migration, phase 3 services, phase 4
UI. Sometimes the right call for a foundation ("sprint 0" layer), rarely for the
whole thing.

- Pros: easy to plan and assign by ownership; the contract is frozen early so
  frontend/backend can parallelise; generated API client regenerated once.
- Cons: nothing usable until the last phase; integration assumptions pile up;
  late discovery of contract mistakes.
- Fits when: the change is mostly a new schema/contract with thin behavior, or
  when the frozen contract docs must be amended before anything else can move.

## 3. By domain / component ownership

One lot per component (e.g. `fred-sdk`, `control-plane`, `frontend`), each owned
by the team/person who knows it, with an integration lot at the end.

- Pros: minimal cross-team coordination; reviews stay in one area; matches
  `CLAUDE.md`'s "smaller, single-purpose PRs".
- Cons: needs a stable contract up front (so usually pairs with a small phase
  1 from pattern 2); integration lot can become the hidden big-bang.
- Fits when: components are loosely coupled by a well-defined contract and the
  work in each is sizeable.

## 4. Strangler / parallel run

New path built beside the old one, traffic switched gradually (flag, team
opt-in, percentage), old path deleted last.

- Pros: reversible at every step; production validation before cutover;
  migration risk spread instead of concentrated.
- Cons: temporary duplication (two code paths, dual-write, two metrics
  sets); more total work; needs an explicit "delete the old path" lot that
  teams tend to skip.
- Fits when: the spec replaces something live (a prompt pipeline, a storage
  backend, an auth path) and downtime or regression is costly.

## 5. Risk-first (spike, then slices)

Lot 0 is a time-boxed spike on the single riskiest unknown (a performance
question, a third-party API behavior, a migration on real data volume). Then
one of the patterns above.

- Pros: the design decision that could invalidate the rest is settled first;
  cheap to abandon.
- Cons: the spike produces no shippable code; can be used as an excuse to delay.
- Fits when: the RFC `Status:` is draft, or an open question in the spec would
  change the architecture if answered the other way.

## 6. Contract-first with stubs

Lot 1 ships the API/SDK contract with stub implementations and generated
clients; behaviors land behind it in any order.

- Pros: frontend and backend unblocked simultaneously; contract reviewed in
  isolation (small diff on the frozen contract docs).
- Cons: stubs in production code paths need guarding; the contract may need a
  revision once real behavior exists.
- Fits when: several consumers wait on the same interface.

## Comparison matrix (template)

| Criterion | Option 1 | Option 2 | Option 3 |
|-----------|----------|----------|----------|
| First shippable increment | after lot 1 (~w2) | after phase 4 | after integration |
| Migration risk | spread | concentrated at cutover | medium |
| Parallelisable | ✗ | ✓ (by layer) | ✓ (by component) |
| Fits existing in-flight work (`openspec/changes/…`) | ✓ | ~ | ✗ |
| Reviewability (PR size) | small | medium | small then large |
| Total effort | + | = | = |

Then one slide: **"We recommend <option> because <one reason tied to the spec>"**,
with the first lot named concretely enough to become a GitHub issue title.
