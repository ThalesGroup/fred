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
import { artifactFileName, composeHtmlDocument, zoomIn, zoomOut, ZOOM_LEVELS } from "./htmlArtifactDocument";

const CSP = "Content-Security-Policy";

describe("composeHtmlDocument", () => {
  it("always injects the CSP meta — bare fragment", () => {
    const out = composeHtmlDocument("<div>hi</div>", "");
    expect(out).toContain(CSP);
    expect(out).toContain("default-src 'none'");
  });

  it("always injects the CSP meta — full document with <head>", () => {
    const out = composeHtmlDocument("<!doctype html><html><head><title>t</title></head><body>x</body></html>", "");
    expect(out).toContain(CSP);
    // The original head content is preserved alongside the injected CSP.
    expect(out).toContain("<title>t</title>");
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

  it("places the CSP before any author subresource in a full document (egress fix)", () => {
    // An author <link>/<img> emitted BEFORE the author's own <head> must still be
    // governed by our CSP — i.e. our meta must appear first in the composed output.
    const doc =
      '<html><link rel="stylesheet" href="https://attacker.example/leak.css"><head></head><body>x</body></html>';
    const out = composeHtmlDocument(doc, "");
    const cspIdx = out.indexOf("Content-Security-Policy");
    const linkIdx = out.indexOf("attacker.example");
    expect(cspIdx).toBeGreaterThan(-1);
    expect(linkIdx).toBeGreaterThan(-1);
    expect(cspIdx).toBeLessThan(linkIdx);
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
});
