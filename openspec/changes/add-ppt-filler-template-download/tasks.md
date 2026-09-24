# Tasks — Download the PPT Filler template an agent already carries

## 1. Reach the stored template

- [x] 1.1 Add the download helper beside the capability's API slice: it builds the
      stored-asset path from the team id (canonicalizing the bare `personal`
      route alias), the agent instance id and the fixed template key, escaping
      each segment the way the runtime's own KF client does, and downloads it
      through `downloadAuthed`; verified by unit tests pinning the path literal,
      the alias resolution, the reserved-character escaping and the file name
- [x] 1.2 Pin the same path literal on the Python side over
      `AgentConfigAssetsAdapter._config_path`, and cross-reference the two from
      its docstring; verified by `test_agent_config_assets_path.py` (4 cases:
      the literal, the canonical personal id, key escape refusal, missing
      team/instance). A frontend-only assertion would have compared the mirror
      to itself

## 2. Carry the agent instance id to the widget

- [x] 2.1 Add the optional agent instance id to `CapabilityConfigWidgetProps`
      beside `teamId`; verified by `npx tsc --noEmit` passing with no widget
      forced to supply it
- [x] 2.2 Thread it from the agent form to the config widgets and to the pack
      options, leaving it absent while an agent is being created; verified by a
      surface test rendering each surface with the id absent. NOT covered by a
      test: `AgentFormBody`'s own `editInstance?.agent_instance_id` passthrough —
      the props are optional, so dropping it would still compile. Covered by the
      manual check in 4.2 only

## 3. The button

- [x] 3.1 Build the shared "Download template" button: enabled only when a
      template is saved (`hasPersistedTemplate`) and the team and instance ids
      are known, carrying the reason it is unavailable on a wrapper (a disabled
      button is unfocusable, so its own `title` would never be announced), and
      reporting a failure through the existing toast; verified by tests covering
      each enabled/disabled reason, both hint texts, and the failure path
- [x] 3.2 Place it in `PptFillerConfigForm` (Advanced view); verified by a test
      asserting it renders and receives this surface's state (the button itself
      is stubbed there — its disabled logic is proven in 3.1, not here)
- [x] 3.3 Place it in `PptFillerPackOptions` (Simple view's PowerPoint pack);
      verified by the same assertions, run over both surfaces from one
      `describe.each`
- [x] 3.4 Confirm a freshly picked, unsaved file leaves the button on the saved
      template and leaves it disabled when nothing is saved; verified by a test
      staging a file in both states
- [x] 3.5 Add the French and English labels for the button, both unavailability
      hints and the failure message; verified by a check that the two locale
      files carry the same keys

## 4. Close-out

- [x] 4.1 Run `make code-quality` from the monorepo root and the frontend suite;
      verified by both reporting zero failures
- [ ] 4.2 Verify the download by hand against a local agent holding a template:
      the file opens in PowerPoint and re-uploads unchanged; verified by the
      round trip succeeding
- [x] 4.3 Run `/code-review` on the diff and address the findings; verified by the
      review reporting nothing outstanding or by each finding being answered
- [ ] 4.4 Record the verification evidence in this change and archive it

## Verification evidence (2026-09-23)

- Frontend suite: 2792 passed, 9 skipped — including 40 tests over this change:
  `templateDownload.test.ts` (path literal, personal-alias resolution,
  reserved-character escaping, file name), `PptTemplateDownloadButton.test.tsx`
  (each enabled/disabled reason, both hints, the failure path) and
  `PptFillerOptionsDownload.test.tsx` (both surfaces through one
  `describe.each`, including the creation flow with no instance id).
- `libs/fred-runtime`: `test_agent_config_assets_path.py`, 4 passed — the Python
  half of the path pin.
- `make code-quality` from the monorepo root: exit 0, zero errors; the only
  output is the pre-existing `nosec` notices in `fred-core` and `fred-runtime`.
- `npx tsc --noEmit` and `prettier --check` on the touched paths: clean.

An independent cold review of the diff ran before this evidence was recorded.
What it caught and what was changed:

- **The personal-space alias.** The helper built `teams/personal/...` from the
  route param, while the bytes are stored under `teams/personal-<uid>/...` — so
  the download would have 404'd for every agent in the personal space, with the
  button enabled and every test passing. Fixed and pinned.
- **A drift guard that did not exist.** The adapter docstring and `design.md`
  claimed the frontend test would fail if the server path changed; it asserted
  the frontend's own template against itself. The Python pin in 1.2 makes the
  claim true.
- **`encodeURI` left `#`, `?` and `&` raw** on a route that takes a real `token`
  query param, and the test's own expected value contradicted its title. Now
  escaped per segment, as the runtime's KF client does.
- **Overclaimed verification lines**, corrected above rather than papered over.
- **A disabled button with no reason**, now carrying one.
- Two findings were accepted rather than fixed and are recorded in `design.md`
  risks: `hasPersistedTemplate` reads stored config rather than the stored file,
  and a staged unsaved file sits beside a button that offers the saved one.

The developer then ran `/code-review` on the three commits (task 4.3). It
returned two findings, both real, both fixed:

- **The alias fix was too broad.** `isPersonalTeamId` also matches an
  already-canonical `personal-<uid>`, so a correct id was discarded and
  re-derived from the session uid — wrong for a caller whose uid differs, and
  `personal-` if the uid were unavailable. The repo's two other `/fs` call sites
  rewrite the bare alias only; now so does this one. The test that claimed to
  cover the canonical case passed vacuously (mocked uid equal to the id under
  test) and now uses a different uid.
- **Duplicating an agent** yields a copy with the slide schema and no stored
  bytes, so the button is enabled and every click 404s. The message now names
  that case ("the template file is missing for this agent, upload it again")
  instead of reporting a generic failure. Recorded in `design.md` risks with why
  probing the object store per panel open was not worth it.

It also sharpened a comment: each side pins the path literal for itself, so
neither drifts unnoticed, but no test compares the two — the docstring now says
exactly that rather than implying a cross-language assertion.

Frontend suite after those fixes: 2797 passed, 9 skipped (42 over this change).
`make code-quality` from the root: exit 0.

Task 4.2 (manual round trip against a local agent) is outstanding: it needs the
developer to run it.
