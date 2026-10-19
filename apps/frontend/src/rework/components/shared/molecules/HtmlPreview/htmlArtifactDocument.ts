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

// Untrusted markup shares sanitization, an opaque iframe sandbox and a restrictive
// CSP across preview/download/new-tab paths. See HTML-ARTIFACT-CAPABILITY-RFC.md.

import DOMPurify, { type Config } from "dompurify";

// Strip script-bearing constructs and nested/remote content; keep inline styles.
const SANITIZE_CONFIG: Config = {
  FORCE_BODY: true,
  FORBID_TAGS: ["script", "iframe", "object", "embed", "base", "meta", "link"],
  RETURN_TRUSTED_TYPE: false,
};

function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, SANITIZE_CONFIG);
}

// Allow inline CSS and embedded image/font data, but deny scripts, network access,
// base URLs and form navigation before any author markup is parsed.
const CSP_META =
  '<meta http-equiv="Content-Security-Policy" content="' +
  "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; " +
  "base-uri 'none'; form-action 'none'" +
  '">';

// Prevent author CSS from closing its style element and injecting HTML.
function neutralizeStyleClose(css: string): string {
  return css.replace(/<\/(style)/gi, "<\\/$1");
}

// Make the layout use the viewport width (the panel), so responsive content fits.
const VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1">';

// Constrain common overflow sources before author styles, which may override them.
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

// Sanitize fragments or full documents into our body after the CSP in our head.
// Preview-only zoom reflows the page; exported documents use the default scale.
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

// Download the same sanitized, CSP-protected document used by the preview.
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

// Escape markup for a double-quoted srcdoc attribute in the trusted new-tab shell.
function escapeForSrcdoc(doc: string): string {
  return doc.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Author content stays inside an opaque sandbox; the same-origin shell is trusted.
const NEW_TAB_SHELL_STYLE =
  "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>";

// Keep all three restrictions in the standalone new-tab document.
export function newTabDocument(html: string, css: string): string {
  const composed = composeHtmlDocument(html, css);
  return (
    `<!doctype html><html><head><meta charset="utf-8">${NEW_TAB_SHELL_STYLE}</head>` +
    `<body><iframe sandbox="" referrerpolicy="no-referrer" srcdoc="${escapeForSrcdoc(composed)}"></iframe></body></html>`
  );
}

// Open the sandboxed shell without an opener, then release the temporary blob URL.
export function openHtmlArtifactInNewTab(html: string, css: string): void {
  const blob = new Blob([newTabDocument(html, css)], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  // Keep the URL alive long enough for the new tab to load, then free it.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
