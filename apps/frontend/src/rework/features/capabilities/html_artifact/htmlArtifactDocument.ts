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
// shell. The markup is untrusted LLM output; NO output path may run script.
// Three independent layers enforce that — content sanitization (A, here), the
// frame `sandbox=""` (B, Preview + newTabDocument), and a CSP `<meta>` (C). Full
// rationale and the verification suite: HTML-ARTIFACT-CAPABILITY-RFC.md §4.7.

import DOMPurify, { type Config } from "dompurify";

// Layer A — strip every script-bearing construct from the author HTML. DOMPurify's
// defaults drop <script>, on* handlers and javascript:/unknown-protocol URLs; we
// also forbid the egress/nested-content tags the static viewer never needs.
// FORCE_BODY keeps a root-level inline <style>; RETURN_TRUSTED_TYPE:false → string.
const SANITIZE_CONFIG: Config = {
  FORCE_BODY: true,
  FORBID_TAGS: ["script", "iframe", "object", "embed", "base", "meta", "link"],
  RETURN_TRUSTED_TYPE: false,
};

function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, SANITIZE_CONFIG);
}

// `default-src 'none'` blocks everything not explicitly allowed (scripts, fetch,
// frames, remote images/fonts/styles); `style-src 'unsafe-inline'` is required for
// author CSS and is safe with scripts disabled; images/fonts only as `data:` URIs;
// no `base-uri` and no `form-action` so a stray <base>/<form> cannot redirect.
const CSP_META =
  '<meta http-equiv="Content-Security-Policy" content="' +
  "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; " +
  "base-uri 'none'; form-action 'none'" +
  '">';

// Neutralize any `</style` sequence in author CSS before it goes inside a <style>
// element. Valid CSS never contains `</style>`; an attacker-crafted value could use
// it to break out of the raw-text style element into HTML context (e.g. inject a
// <meta http-equiv="refresh">). The iframe sandbox (no allow-scripts) + CSP already
// block script and network egress, but this closes the markup-injection breakout too
// (defense in depth). Inserting a backslash keeps the HTML parser from seeing a real
// closing tag; the CSS parser treats the residue as an ignorable bad token.
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
  "html{box-sizing:border-box}*,*::before,*::after{box-sizing:inherit}" +
  "html,body{margin:0}body{padding:12px;overflow-wrap:break-word;word-break:break-word}" +
  "img,svg,video,canvas{max-width:100%;height:auto}" +
  "table{max-width:100%}pre{max-width:100%;overflow-x:auto}" +
  "</style>";

/** Head content that opens every composed document, BEFORE any author markup. */
function headInjection(css: string): string {
  const authorStyle = css ? `<style>${neutralizeStyleClose(css)}</style>` : "";
  return `<meta charset="utf-8">${VIEWPORT_META}${CSP_META}${FIT_STYLE}${authorStyle}`;
}

/**
 * Compose the artifact into one self-contained HTML document string.
 *
 * The author markup (a bare fragment OR a full `<!doctype html>…` document) is
 * first SANITIZED (Layer A), then ALWAYS placed inside OUR shell's <body>, never
 * spliced into an author-provided <head>/<html>. This guarantees our CSP <meta>
 * is the FIRST thing the parser reaches, so it governs EVERY author subresource —
 * a meta CSP only applies to content parsed after it, so any `<img>` an author
 * put before their own <head> would otherwise fetch from the network before the
 * policy took effect. Sanitization drops head-only tags (<title>) and the
 * forbidden set (<script>/<link>/…); a full document's remaining meaningful body
 * content still renders — now under our already-active CSP.
 *
 * `zoom` (default 1) applies a browser-like zoom to the PREVIEW only, via the CSS
 * `zoom` property so content actually reflows (a wide fixed-width page shrinks to
 * fit when zoomed out, unlike a purely visual transform). Download / open-in-new-tab
 * pass no zoom, so the exported document is always 100%. `zoom` is a clamped number
 * from the viewer's own controls, never user text — no injection surface.
 */
export function composeHtmlDocument(html: string, css: string, zoom = 1): string {
  const zoomStyle = zoom !== 1 ? `<style>html{zoom:${zoom}}</style>` : "";
  const safeHtml = sanitizeHtml(html);
  return `<!doctype html><html><head>${headInjection(css)}${zoomStyle}</head><body>${safeHtml}</body></html>`;
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

/** A safe download filename derived from the artifact title (always ends in .html). */
export function artifactFileName(title: string): string {
  const base = (title || "artifact")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `${base || "artifact"}.html`;
}

/**
 * Trigger a client-side download of the composed document. The markup is inline on
 * the part, so this is a plain blob save — no network, no bearer (unlike the
 * bearer-protected file downloads of ppt_filler / writable_document).
 */
export function downloadHtmlArtifact(html: string, css: string, title: string): void {
  const doc = composeHtmlDocument(html, css);
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

// Escape a document so it can ride safely inside a double-quoted `srcdoc="…"`
// attribute: `"` (would end the attribute) and `&` (would start an entity) MUST
// be escaped; `<`/`>` are escaped too so the value can never be misparsed. The
// browser reverses these entities when it parses srcdoc, yielding the exact doc.
function escapeForSrcdoc(doc: string): string {
  return doc.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// The new tab's TOP document — trusted, author-free, its only body a sandboxed
// iframe. Keeping the artifact one level down in `sandbox=""` restores the
// browser-enforced no-script guarantee (Layer B) even though a blob: URL is
// same-origin with the app: the only same-origin document is this shell, which
// carries no author markup.
const NEW_TAB_SHELL_STYLE =
  "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>";

/**
 * The self-contained document opened in a new browser tab: the sanitized+CSP
 * composed artifact (Layers A & C) wrapped in a trusted shell whose sandboxed
 * iframe hosts it (Layer B). Exported for unit testing; `openHtmlArtifactInNewTab`
 * is the side-effecting caller.
 */
export function newTabDocument(html: string, css: string): string {
  const composed = composeHtmlDocument(html, css);
  return (
    `<!doctype html><html><head><meta charset="utf-8">${NEW_TAB_SHELL_STYLE}</head>` +
    `<body><iframe sandbox="" referrerpolicy="no-referrer" srcdoc="${escapeForSrcdoc(composed)}"></iframe></body></html>`
  );
}

/**
 * Open the artifact full-size in a new browser tab — the escape hatch for content
 * too wide for the side panel. Loads a blob: URL of the sandboxed-shell document
 * (`newTabDocument`), opened with `noopener` so it cannot reach `window.opener`.
 */
export function openHtmlArtifactInNewTab(html: string, css: string): void {
  const blob = new Blob([newTabDocument(html, css)], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  // Keep the URL alive long enough for the new tab to load, then free it.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
