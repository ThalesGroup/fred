# fred-capability-html-artifact

A Fred agent capability (`html_artifact`) that lets an agent produce an
**HTML/CSS/JS artifact** rendered live in a **sandboxed viewer beside the chat** —
the "artifact" experience. An artifact must be self-contained, with no external
resource and no network access.

**JavaScript is granted per team.** It is off unless an administrator turns on
`allow_javascript` for that team; every team keeps HTML/CSS generation either way.
See "JavaScript posture" below.

Design: `docs/swift/rfc/HTML-ARTIFACT-CAPABILITY-RFC.md` (issue #2478), per-team
gating in `openspec/specs/html-artifact-javascript-policy/spec.md`.

## What it ships

- **Tool** `render_html_artifact(title, html, css, artifact_id?)` — HTML and CSS
  kept separate (for the viewer's tabs). Combined size is capped at 256 KB.
- **Chat part** `HtmlArtifactPart` (`type="html_artifact"`) carrying the markup
  **inline** — no owned table, no router, no migration (v1 is read-only; chat
  `ui_parts` persist across reload).
- **Prompt fragment** steering the model to call the tool (and to keep the artifact
  self-contained) instead of pasting code into the chat. Two variants, selected by
  the team's JavaScript posture, so a restricted team is never offered script it
  cannot run.
- **Team setting** `allow_javascript` (boolean, default off), declared through
  `team_settings_fields` and filled from the Features admin page.
- **Side panel** `html_artifact_pane` (frontend): read-only tabs **Preview**
  (sandboxed `<iframe srcdoc>`) / **HTML** / **CSS** + download.

`execution_models=("react",)`: the prompt overlay is a `wrap_model_call` hook, so
the tool is carried by the capability's middleware (mirrors `writable_document`).

## Registration

Installing this package IS the registration — the `fred.capabilities` entry point
in `pyproject.toml` points the fred-agents pod at `HtmlArtifactCapability`. It is
wired into the pod as an editable path dependency of `apps/fred-agents`.

## JavaScript posture

Running model-authored script is an operator decision, taken team by team through
`allow_javascript`. It reaches the capability as `ctx.team_settings` and is
enforced twice:

- **At write time** — `render_html_artifact` refuses a page containing script for
  a team that is not opted in, returning a recoverable error so the model
  re-renders statically. Script a team may not run is never stored.
- **At display time** — the viewer resolves the team's *current* right each time
  it opens, not a flag recorded when the page was produced. Withdrawing the right
  therefore makes previously generated artifacts inert too.

The restricted mode is **not** a return to the retired DOMPurify pass. The
artifact frame simply carries no sandbox token, so nothing executes — by browser
guarantee rather than by recognizing what to remove. The CSP below stays active in
both modes: markup alone (`<img src="https://host/?d=…">`) still reaches the
network.

## Security

The markup is untrusted LLM output and it may run script, so it is **isolated
rather than sanitized**. The backend carries only inert strings; safe rendering is
a frontend concern (RFC §4.7). An artifact frame carries `sandbox="allow-scripts"`
for an opted-in team and **no token at all** otherwise, never
`allow-same-origin` — an opaque origin with no reach into the app's DOM, cookies
or storage — under a CSP of `default-src 'none'` plus `script-src 'unsafe-inline'`
and `webrtc 'block'`, so inline script runs (where permitted) but no fetch, XHR,
WebSocket or remote subresource is possible.

A CSP cannot stop a document **navigating itself**, which is a full-bandwidth
exfiltration channel, so all three paths — preview, new tab and `.html`
download — render a trusted shell that bootstraps the artifact into a `blob:`-URL
child frame and carries `frame-src blob:`. The shell is used in both modes: a
saved file opened by double-click is the top document on `file://` with nothing
else to deny script, so the posture has to travel inside the document. That directive on the *parent* is the
only thing that blocks the navigation; it needs a matchable URL, which is why the
artifact is not passed inline as `srcdoc`. Verified in Chrome 153, `file://`
included.

## Dev

```
make code-quality   # ruff + format + type-check
make test           # offline unit tests
```
