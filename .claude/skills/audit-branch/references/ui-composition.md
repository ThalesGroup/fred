# Review UI composition

Use for reusable UI exports and event/focus changes. Select combinations from
real consumers and supported public components; do not enumerate every possible
pair or report a missing test as a defect.

## Discover the event owners

Start with changed components and their imports, then follow shared event and
focus mechanisms into dependencies outside the diff. These read-only commands
are discovery aids, not a correctness gate (run from the repository root):

```sh
rg -n 'addEventListener|removeEventListener|onKeyDown|onPointerDown|onClick' apps/frontend/src/rework/components/shared apps/frontend/src/rework/core/hooks
rg -n 'preventDefault|defaultPrevented|stopPropagation|stopImmediatePropagation|createPortal|activeElement|focus\(' apps/frontend/src/rework/components/shared
rg -n 'Dialog|InlineDrawer|Select' libs/frontend/fixtures/react-consumer/src apps/frontend/src/rework
```

Narrow results to the changed surface and plausible composition partners. Record
which component owns each action, the listener target (element/document/window),
capture/bubble phase, registration/cleanup, and portal DOM location. A global
listener makes unrelated visible siblings potential participants too.

## Follow one user action across boundaries

For a nested overlay, test the child opened after its parent and both mounted
open; listener registration order can differ. Press Escape with focus inside
the child. Verify the child's callback count, the parent's callback count, the
remaining visible context and restored focus. Test the next Escape after the
child closes. Include close/reopen or remount when it changes listener lifetime.

Do not infer isolation from preventDefault alone: it does not stop propagation.
A defaultPrevented check only helps listeners that run after consumption.
stopPropagation does not suppress other listeners on the same target. Validate
the proposed ownership rule under both registration orders rather than merely
adding a guard that passes one scenario.

Apply the same reasoning where relevant to Enter inside forms, pointer actions
inside clickable rows, portaled menus, focus restoration and native reset. Test
both the intended child effect and the absence of an unintended parent effect.
Avoid prescribing a new global overlay manager without evidence it is needed.

## Use the existing verification tools

Use existing component tests for callback/state evidence, and the packed
consumer with Chromium for browser event order, focus, portals and default
actions. Dispatching a synthetic event in a DOM simulator alone does not prove
native keyboard/reset behavior. Prefer actual keyboard actions in the browser.

During a read-only review, temporary reproduction artifacts may be created and
removed without changing production or tracked tests. Report the exact command,
HEAD, observed output and limitations. An author can subsequently retain the
regression in the existing suite. Never count a keyword search as a passed test.

## Compare behavior, not the number of findings

For an extraction, rerun the representative old valid usage against base and
head. Record what changed and whether the task authorized it. For example,
fixing a counter by rejecting a previously supported native input mode does not
preserve extraction compatibility.

A replay of a known missed case checks that the procedure is executable; it
cannot establish independent detection. Use the evaluation procedure's held-out
cases and fixed controls before claiming improved generalization. Preserve
unreviewed combinations as explicit exclusions rather than claiming completeness.
