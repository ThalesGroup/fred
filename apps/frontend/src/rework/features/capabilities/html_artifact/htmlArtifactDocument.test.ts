// @vitest-environment jsdom
//
// DOMPurify (composeHtmlDocument's sanitizer) needs a full, browser-faithful DOM;
// happy-dom's is too partial and strips all tags to text, so these tests would
// pass trivially and prove nothing. jsdom is DOMPurify's reference environment.
//
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

// Tests for the security-critical composition (RFC §4.7): the CSP <meta> must be
// present in EVERY composed document, CSS must be injected, and both a full
// document and a bare fragment must compose to a valid single document.

import { describe, expect, it } from "vitest";
import {
  artifactFileName,
  composeHtmlDocument,
  newTabDocument,
  zoomIn,
  zoomOut,
  ZOOM_LEVELS,
} from "./htmlArtifactDocument";

const CSP = "Content-Security-Policy";

describe("composeHtmlDocument", () => {
  it("always injects the CSP meta — bare fragment", () => {
    const out = composeHtmlDocument("<div>hi</div>", "");
    expect(out).toContain(CSP);
    expect(out).toContain("default-src 'none'");
  });

  it("always injects the CSP meta — full document with <head>", () => {
    const out = composeHtmlDocument(
      "<!doctype html><html><head><title>t</title></head><body><p>body-text</p></body></html>",
      "",
    );
    expect(out).toContain(CSP);
    // Sanitization keeps the meaningful body content (a stray inert <title>
    // node may survive in the body, but no script/handler does — see below).
    expect(out).toContain("body-text");
  });

  it("always injects the CSP meta — full document WITHOUT <head>", () => {
    const out = composeHtmlDocument("<html><body>x</body></html>", "");
    expect(out).toContain(CSP);
    expect(out.toLowerCase()).toContain("<head>");
  });

  it("wraps a bare fragment into a full document with the fragment in the body", () => {
    const out = composeHtmlDocument("<p>hello</p>", "");
    expect(out.toLowerCase()).toContain("<!doctype html>");
    expect(out).toContain("<body><p>hello</p></body>");
  });

  it("injects the author CSS as its own <style> only when present", () => {
    const withCss = composeHtmlDocument("<div>x</div>", "div { color: red; }");
    expect(withCss).toContain("<style>div { color: red; }</style>");
    // Two <style> tags: the base fit stylesheet + the author's.
    expect((withCss.match(/<style>/g) ?? []).length).toBe(2);

    const noCss = composeHtmlDocument("<div>x</div>", "");
    expect(noCss).not.toContain("color: red");
    // Only the base fit stylesheet, no author <style>.
    expect((noCss.match(/<style>/g) ?? []).length).toBe(1);
  });

  it("injects a viewport meta and a fit-to-width base stylesheet", () => {
    const out = composeHtmlDocument("<div>x</div>", "");
    expect(out).toContain('name="viewport"');
    // Media/tables are capped to the panel width so content fits the viewer.
    expect(out).toContain("max-width:100%");
  });

  it("never emits an app-URL <base> or form-action (CSP forbids both)", () => {
    const out = composeHtmlDocument("<form></form>", "");
    expect(out).toContain("base-uri 'none'");
    expect(out).toContain("form-action 'none'");
  });

  it("places the CSP before any surviving author subresource (egress ordering)", () => {
    // An <img> survives sanitization (it is presentational); its external fetch
    // must still be governed by our CSP, so the meta must appear BEFORE it.
    const doc = '<html><img src="https://attacker.example/leak.png"><head></head><body>x</body></html>';
    const out = composeHtmlDocument(doc, "");
    const cspIdx = out.indexOf("Content-Security-Policy");
    const imgIdx = out.indexOf("attacker.example");
    expect(cspIdx).toBeGreaterThan(-1);
    expect(imgIdx).toBeGreaterThan(-1);
    expect(cspIdx).toBeLessThan(imgIdx);
  });

  it("strips egress / navigation tags outright (<link>, <base>, <meta>)", () => {
    const doc =
      '<link rel="stylesheet" href="https://attacker.example/leak.css">' +
      '<base href="https://attacker.example/">' +
      '<meta http-equiv="refresh" content="0;url=https://attacker.example">' +
      "<p>ok</p>";
    const out = composeHtmlDocument(doc, "");
    expect(out).toContain("<p>ok</p>");
    // None of the author's egress/navigation tags survive to the body.
    expect(out).not.toContain("attacker.example");
    expect(out.toLowerCase()).not.toContain("<link");
    expect(out.toLowerCase()).not.toContain("<base");
    expect(out.toLowerCase()).not.toContain("refresh");
  });

  it("neutralizes a </style> breakout in the CSS", () => {
    // Author CSS that tries to escape the <style> element and inject markup.
    const out = composeHtmlDocument("<div>x</div>", '</style><meta http-equiv="refresh" content="0;url=http://evil">');
    // The attacker's `</style` is neutralized (backslash inserted) ...
    expect(out).toContain("<\\/style");
    // ... so only the legitimate closes survive (base fit style + author style =
    // 2), not a third from the injected one.
    expect((out.match(/<\/style>/gi) ?? []).length).toBe(2);
    // ... and the injected <meta> stays INSIDE the (inert) author style element,
    // before its closing tag (the LAST </style>) — never in HTML context.
    const metaIdx = out.indexOf("http-equiv");
    const authorCloseIdx = out.lastIndexOf("</style>");
    expect(metaIdx).toBeGreaterThan(-1);
    expect(metaIdx).toBeLessThan(authorCloseIdx);
  });
});

// Layer A — the sanitizer removes every script-bearing construct at the single
// composition chokepoint, so no output path carries executable JS in its markup.
// Each payload plants the marker `__pwn`; a clean composition contains neither the
// marker nor any script/handler/URL that would have run it.
describe("composeHtmlDocument strips executable JS (RFC §4.7 Layer A)", () => {
  const VECTORS: [label: string, payload: string][] = [
    ["<script> tag", "<script>window.__pwn=1</script>"],
    ["img onerror", '<img src=x onerror="window.__pwn=1">'],
    ["svg onload", '<svg onload="window.__pwn=1"></svg>'],
    ["svg <script>", "<svg><script>window.__pwn=1</script></svg>"],
    ["javascript: href", '<a href="javascript:window.__pwn=1">x</a>'],
    ["inline onclick", '<div onclick="window.__pwn=1">x</div>'],
    ["iframe js src", '<iframe src="javascript:window.__pwn=1"></iframe>'],
    ["object data", '<object data="data:text/html,<script>window.__pwn=1</script>"></object>'],
    ["embed", '<embed src="data:text/html,window.__pwn=1">'],
    ["vbscript: href", '<a href="vbscript:window.__pwn=1">x</a>'],
    ["formaction js", '<form><button formaction="javascript:window.__pwn=1">go</button></form>'],
    ["mutation xss", '<noscript><p title="</noscript><img src=x onerror=window.__pwn=1>">'],
    ["body onload", '<body onload="window.__pwn=1"><p>x</p></body>'],
  ];

  it.each(VECTORS)("neutralizes %s", (_label, payload) => {
    const out = composeHtmlDocument(payload, "");
    expect(out.toLowerCase()).not.toContain("<script");
    expect(out).not.toContain("__pwn");
    expect(out.toLowerCase()).not.toContain("javascript:");
    expect(out.toLowerCase()).not.toContain("vbscript:");
    // No `on…=` event-handler attribute survives (our own head markup has none).
    expect(out).not.toMatch(/\son[a-z]+\s*=/i);
  });

  it("keeps legitimate static markup and inline <style>", () => {
    const out = composeHtmlDocument(
      '<section class="card"><h1>Title</h1><style>.card{color:red}</style></section>',
      "",
    );
    expect(out).toContain("<h1>Title</h1>");
    expect(out).toContain(".card{color:red}");
  });
});

// Layer B — the new tab's TOP document is a trusted, author-free shell whose only
// body is a sandboxed iframe; the artifact rides escaped inside its srcdoc.
describe("newTabDocument (RFC §4.7 Layer B — sandboxed shell)", () => {
  it('hosts the artifact in a sandbox="" iframe with the content escaped in srcdoc', () => {
    const out = newTabDocument("<h1>hi</h1>", "");
    expect(out).toContain('<iframe sandbox=""');
    // The composed document rides escaped inside srcdoc — its markup never parses
    // at the shell's (author-free, same-origin) top level.
    expect(out).toContain("&lt;h1&gt;hi&lt;/h1&gt;");
    expect(out).not.toContain("<h1>hi</h1>");
  });

  it("never enables scripts or same-origin on the shell iframe", () => {
    const out = newTabDocument("<p>x</p>", "");
    expect(out).not.toContain("allow-scripts");
    expect(out).not.toContain("allow-same-origin");
  });

  it("escapes double quotes so author content cannot break out of srcdoc", () => {
    const out = newTabDocument('<a title="x">"</a>', "");
    // Every author/content double-quote is entity-escaped; the only raw quotes
    // left are the shell's own attribute delimiters.
    expect(out).toContain("&quot;");
  });

  it("passes a JS payload through inert — no script survives even one level down", () => {
    const out = newTabDocument('<img src=x onerror="window.__pwn=1">', "");
    expect(out).not.toContain("__pwn");
    expect(out.toLowerCase()).not.toContain("onerror");
  });
});

describe("composeHtmlDocument zoom", () => {
  it("injects a CSS zoom rule only when zoom !== 1", () => {
    expect(composeHtmlDocument("<div>x</div>", "", 0.5)).toContain("zoom:0.5");
    expect(composeHtmlDocument("<div>x</div>", "")).not.toContain("zoom:");
    expect(composeHtmlDocument("<div>x</div>", "", 1)).not.toContain("zoom:");
  });
});

describe("zoom stepping", () => {
  it("steps down and clamps at the smallest level", () => {
    expect(zoomOut(1)).toBe(0.9);
    expect(zoomOut(ZOOM_LEVELS[0])).toBe(ZOOM_LEVELS[0]);
  });

  it("steps up and clamps at the largest level", () => {
    expect(zoomIn(1)).toBe(1.1);
    expect(zoomIn(ZOOM_LEVELS[ZOOM_LEVELS.length - 1])).toBe(ZOOM_LEVELS[ZOOM_LEVELS.length - 1]);
  });
});

describe("artifactFileName", () => {
  it("slugifies the title and always ends in .html", () => {
    expect(artifactFileName("My Landing Page!")).toBe("my-landing-page.html");
  });

  it("falls back to a default for an empty/blank title", () => {
    expect(artifactFileName("   ")).toBe("artifact.html");
    expect(artifactFileName("")).toBe("artifact.html");
  });

  it("uses the given extension (e.g. png) when provided", () => {
    expect(artifactFileName("My Landing Page!", "png")).toBe("my-landing-page.png");
    expect(artifactFileName("", "png")).toBe("artifact.png");
  });
});
