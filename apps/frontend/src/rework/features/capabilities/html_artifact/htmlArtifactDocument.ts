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
// document for the Preview iframe (`srcdoc`) and the download blob.
//
// SECURITY (HTML-ARTIFACT-CAPABILITY-RFC.md §4.7): the markup is untrusted LLM
// output. The primary control is the iframe's `sandbox=""` (no `allow-scripts`,
// no `allow-same-origin`) applied where the iframe is mounted — no script runs and
// the frame is an opaque origin with no access to the app. This module adds
// defense-in-depth: it ALWAYS injects a restrictive CSP `<meta>` into the composed
// document head, so even absent the sandbox no external resource can load and no
// script can run. The two controls are independent by design.

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

/** Head content that opens every composed document, BEFORE any author markup. */
function headInjection(css: string): string {
  const style = css ? `<style>${neutralizeStyleClose(css)}</style>` : "";
  return `<meta charset="utf-8">${CSP_META}${style}`;
}

/**
 * Compose the artifact into one self-contained HTML document string.
 *
 * The author markup (a bare fragment OR a full `<!doctype html>…` document) is
 * ALWAYS placed inside OUR shell's <body>, never spliced into an author-provided
 * <head>/<html>. This guarantees our CSP <meta> is the FIRST thing the parser
 * reaches, so it governs EVERY author subresource — a meta CSP only applies to
 * content parsed after it, so any `<link>`/`<img>` an author put before their own
 * <head> would otherwise fetch from the network before the policy took effect
 * (the sandbox blocks script but not subresource fetches). A full document's own
 * <html>/<head>/<body> tags are ignored by the parser inside our body, but its
 * meaningful content still renders — now under our already-active CSP.
 */
export function composeHtmlDocument(html: string, css: string): string {
  return `<!doctype html><html><head>${headInjection(css)}</head><body>${html}</body></html>`;
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
