# fred-capability-html-artifact

A Fred agent capability (`html_artifact`) that lets an agent produce an
**HTML/CSS/JS artifact** rendered live in a **sandboxed viewer beside the chat** —
the "artifact" experience. JavaScript is allowed, so an artifact can have tabs,
animations and interaction; it must be self-contained, with no external resource
and no network access.

Design: `docs/swift/rfc/HTML-ARTIFACT-CAPABILITY-RFC.md` (issue #2478).

## What it ships

- **Tool** `render_html_artifact(title, html, css, artifact_id?)` — HTML and CSS
  kept separate (for the viewer's tabs). Combined size is capped at 256 KB.
- **Chat part** `HtmlArtifactPart` (`type="html_artifact"`) carrying the markup
  **inline** — no owned table, no router, no migration (v1 is read-only; chat
  `ui_parts` persist across reload).
- **Prompt fragment** steering the model to call the tool (and to keep the artifact
  self-contained) instead of pasting code into the chat.
- **Side panel** `html_artifact_pane` (frontend): read-only tabs **Preview**
  (sandboxed `<iframe srcdoc>`) / **HTML** / **CSS** + download.

`execution_models=("react",)`: the prompt overlay is a `wrap_model_call` hook, so
the tool is carried by the capability's middleware (mirrors `writable_document`).

## Registration

Installing this package IS the registration — the `fred.capabilities` entry point
in `pyproject.toml` points the fred-agents pod at `HtmlArtifactCapability`. It is
wired into the pod as an editable path dependency of `apps/fred-agents`.

## Security

The markup is untrusted LLM output and it runs script, so it is **isolated rather
than sanitized**. The backend carries only inert strings; safe rendering is a
frontend concern (RFC §4.7). Every artifact frame is `sandbox="allow-scripts"`
**without** `allow-same-origin` — an opaque origin with no reach into the app's DOM,
cookies or storage — under a CSP of `default-src 'none'` plus
`script-src 'unsafe-inline'` and `webrtc 'block'`, so inline script runs but no
fetch, XHR, WebSocket or remote subresource is possible.

A CSP cannot stop a document **navigating itself**, which is a full-bandwidth
exfiltration channel, so all three scripting paths — preview, new tab and `.html`
download — render a trusted shell that bootstraps the artifact into a `blob:`-URL
child frame and carries `frame-src blob:`. That directive on the *parent* is the
only thing that blocks the navigation; it needs a matchable URL, which is why the
artifact is not passed inline as `srcdoc`. Verified in Chrome 153, `file://`
included.

## Dev

```
make code-quality   # ruff + format + type-check
make test           # offline unit tests
```
