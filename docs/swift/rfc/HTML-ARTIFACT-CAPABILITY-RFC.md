# RFC — HTML Artifact Capability: agent-generated static HTML/CSS with a sandboxed preview

**Status:** Draft for developer review
**Author:** Maxime Daragon
**Date:** 2026-08-31
**Area:** `fred-runtime` (new capability package), `frontend`
**Related:** `AGENT-CAPABILITY-PRESENTATION.html` (part-renderer / side-panel
architecture), `CAPABILITY-EXECUTION-FLOW-RFC.md`, the `add-fred-capability`
skill, and the `writable_document` capability
(`libs/fred-capability-writable-document/`) used as the reference vertical.

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

1. Give an agent one tool to emit a **static** HTML/CSS artifact.
2. Render it live in a **dedicated viewer that opens to the right of the chat**,
   with a tabbed, **read-only** surface: **Preview** (rendered) / **HTML**
   (source) / **CSS** (source).
3. Render untrusted, LLM-generated markup **safely** — no script execution, no
   network egress, no access to the app's origin or storage.
4. Let the user **download** the artifact as a self-contained `.html`.
5. Reuse the shipped capability-presentation machinery (typed chat part +
   side panel + part-renderer registry) rather than inventing a parallel path;
   mirror `writable_document` end to end.

---

## 3. Non-goals (v1)

- **No JavaScript.** The artifact is HTML + CSS only; the sandbox forbids script
  execution regardless of what the model emits (§4.7).
- **No editing / no server-side persistence.** The viewer is read-only. There is
  no owned table, no router, no PUT. (Explicitly deferred — see §8.)
- **No agent read-back.** The agent does not re-ingest a prior artifact to
  continue editing it (deferred with persistence).
- **No per-agent configuration.** The capability needs no agent-creation config.
- **Not a general web sandbox / not a code runner.** Static markup preview only.

---

## 4. Design

### 4.1 Lane and shape

Full **capability package** lane (per the `add-fred-capability` skill §7 table):
it contributes a **custom chat part** (the artifact card) and a **side panel**
(the viewer), neither of which the MCP lane can express. It is
`execution_models = ("react",)` because it carries a system-prompt fragment via a
`middleware()` override (§4.5), exactly like `writable_document`/`ppt_filler`.

New package: `libs/fred-capability-html-artifact/fred_capability_html_artifact/`,
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
the chat. Emit static HTML/CSS only; no `<script>`, no external resources."

### 4.6 Frontend — the viewer

New plugin `apps/frontend/src/rework/features/capabilities/html_artifact/`,
mirroring the `writable_document` plugin:

- **Card renderer** `HtmlArtifactCardRenderer` — compact in-message card (icon,
  title, "Open preview" button, download). Feeds each part into the slice and
  auto-opens the panel on a live render (same heuristic/probe pattern already used
  by the two shipped capabilities).
- **Side panel** `HtmlArtifactPane` — opens right of the chat. **This is the one
  net-new UI primitive.** Tabbed, all **read-only**:
  - **Preview** — a sandboxed `<iframe srcdoc={composed} sandbox="...">` (§4.7).
  - **HTML** — the `html` source, syntax-highlighted, not editable. Reuses the
    existing `CodeBlock` molecule (`react-syntax-highlighter`, already a frontend
    dependency) — no new dependency (§9.3 resolved).
  - **CSS** — the `css` source, via the same `CodeBlock`, not editable.
  - **Download** — the composed self-contained `.html` (CSS inlined), via the
    existing authed/blob download pattern.
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

### 4.7 Security — the sandbox (the load-bearing part)

The markup is untrusted LLM output. The preview MUST NOT be able to run script,
reach the network, touch the app origin, or navigate the top frame.

- **`<iframe sandbox>` WITHOUT `allow-scripts` and WITHOUT `allow-same-origin`.**
  No JS runs (covers inline handlers, `<script>`, `javascript:` URLs); the frame
  is an opaque origin with no access to `window.parent`, cookies, or storage.
- **`srcdoc`** (never `src` to an app URL) so the content is inert document text,
  same-document, no navigation to app routes.
- **A restrictive CSP `<meta http-equiv>` injected into the composed head:**
  `default-src 'none'; style-src 'unsafe-inline'; img-src data:;
  font-src data:; base-uri 'none'; form-action 'none'`. No external fetch, no
  remote images/fonts/styles, images only as `data:` URIs. (`'unsafe-inline'` for
  styles is required for author CSS and is safe with scripts disabled.)
- **`sandbox` also omits `allow-top-navigation` and `allow-popups`** — a link can
  render but cannot navigate the app or open windows.
- Defense in depth: the two controls are independent (sandbox blocks script even
  if a CSP is bypassed; CSP blocks egress even if a sandbox flag regresses).

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
5. **Allow JavaScript (full artifacts).** Deferred: large security surface
   (needs `allow-scripts`, a hardened CSP, and threat review). v1 is static; the
   design leaves room to widen the sandbox later without a rewrite.

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
`/security-review` on the diff, with explicit attention to — script execution
blocked (inline handlers, `<script>`, `javascript:`), no `allow-same-origin`, no
network egress, no top-navigation, and correct CSP composition for both full
documents and wrapped fragments. Ship no artifact preview that can execute script
or reach the app origin.

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
