// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { prepareMermaidSvg, serializeMermaidSvg } from "./mermaidSvg";

const example = `<svg id="raw" aria-labelledby="title"><title id="title">Example</title>
<style>@import url('https://fonts.googleapis.com/css?family=Inter');
@font-face {font-family:remote;src:url(https://example.com/font.woff2)}
svg {--bg:var(--surface-container)} text {font-family:Inter;fill:var(--on-surface)}
#raw .node {animation:pulse 1s} @keyframes pulse {from {opacity:.5} to {opacity:1}}
</style><defs><marker id="arrow"><path d="M0,0 L4,2"/></marker></defs>
<g id="node" class="node"><text>Question</text></g>
<path marker-end="url(#arrow)" style="stroke:var(--primary);filter:url('#arrow')"/>
<use href="#node"/></svg>`;

describe("SVG view isolation", () => {
  it("exports a complete standalone white SVG with its scope, theme, HTML labels and references", () => {
    const host = document.createElement("div");
    host.id = "download";
    host.innerHTML = prepareMermaidSvg(
      '<svg viewBox="-10 -20 1200 600" style="--surface-container:#101010;--on-surface:#ffffff;--primary:#00658c;font-family:Arial;font-size:16px"><style>text{fill:var(--on-surface)}</style><defs><marker id="arrow"><path d="M0 0L4 2"/></marker></defs><text>Full diagram</text><path marker-end="url(#arrow)"/><foreignObject width="100" height="20"><div xmlns="http://www.w3.org/1999/xhtml">HTML label</div></foreignObject></svg>',
      host.id,
    );
    document.body.append(host);
    try {
      const source = host.querySelector("svg")!;
      const before = host.innerHTML;
      const output = new DOMParser().parseFromString(serializeMermaidSvg(source), "image/svg+xml");
      expect(output.querySelector("parsererror")).toBeNull();
      expect(output.documentElement.id).toBe("download");
      expect(output.documentElement.getAttribute("viewBox")).toBe("0 0 1200 600");
      expect(output.documentElement.firstElementChild?.getAttribute("fill")).toBe("#ffffff");
      expect(output.querySelector("svg svg")!.getAttribute("viewBox")).toBe("-10 -20 1200 600");
      expect(output.documentElement.style.getPropertyValue("--on-surface")).toBe("#ffffff");
      expect(output.querySelector("style")!.textContent).toContain("#download text");
      expect(output.querySelector("foreignObject")!.getAttribute("style")).toContain("overflow: visible");
      const reference = output
        .querySelector("[marker-end]")!
        .getAttribute("marker-end")!
        .match(/#([^)'"\s]+)/)![1];
      expect(output.getElementById(reference)?.localName).toBe("marker");
      expect(output.documentElement.textContent).toContain("Full diagram");
      expect(output.documentElement.textContent).toContain("HTML label");
      expect(host.innerHTML).toBe(before);
    } finally {
      host.remove();
    }
  });

  it("lets the viewer fit the SVG without losing its natural size or geometry", () => {
    const host = document.createElement("div");
    host.innerHTML = prepareMermaidSvg(
      '<svg viewBox="0 0 1200 600" width="100%" height="600" style="max-width:1200px;min-width:1200px;width:100%;height:600px;color:var(--on-surface)"><path d="M0 0L1200 600"/><text>Family</text></svg>',
      "sized",
    );
    const svg = host.querySelector("svg")!;
    expect(svg.getAttribute("viewBox")).toBe("0 0 1200 600");
    expect(svg.getAttribute("width")).toBe("1200");
    for (const property of ["min-width", "max-width", "width", "height"])
      expect(svg.style.getPropertyValue(property)).toBe("");
    expect(svg.querySelector("path")!.getAttribute("d")).toBe("M0 0L1200 600");
    expect(svg.textContent).toBe("Family");
  });

  it("gives every inline/enlarged view its own IDs, references, styles and keyframes", () => {
    const host = document.createElement("div");
    host.innerHTML = ["firstInline", "firstEnlarged", "secondInline"]
      .map((scope) => `<div id="${scope}">${prepareMermaidSvg(example, scope)}</div>`)
      .join("");
    const ids = [...host.querySelectorAll("[id]")].map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const wrapper of [...host.children]) {
      const svg = wrapper.querySelector("svg")!;
      for (const attr of ["marker-end", "style"]) {
        const value = svg.querySelector("path[marker-end]")!.getAttribute(attr)!;
        for (const match of value.matchAll(/url\(["']?#([^)'"\s]+)/g))
          expect(wrapper.querySelector(`[id="${match[1]}"]`)).not.toBeNull();
      }
      expect(wrapper.querySelector(`[id="${svg.getAttribute("aria-labelledby")}"]`)).not.toBeNull();
      expect(svg.querySelector("style")!.textContent).toContain(`#${wrapper.id} text`);
      expect(svg.querySelector("style")!.textContent).toContain(`@keyframes ${wrapper.id}-animation-0`);
      expect(svg.innerHTML).not.toContain("https://");
    }
  });

  it("sanitizes script-bearing markup, URLs and handlers while keeping labels and paths", () => {
    const raw =
      '<svg onload="alert(1)"><script>alert(1)</script><a href="javascript:alert(1)"><text>Safe label</text></a><path d="M0 0L10 10"/></svg>';
    const output = prepareMermaidSvg(raw, "safe");
    expect(output).not.toMatch(/<script|onload|javascript:/i);
    expect(output).toContain("Safe label");
    expect(output).toContain('d="M0 0L10 10"');
  });

  it("keeps absolute same-document references inside each renamed view", () => {
    const absolute = new URL("#arrow", document.URL).href;
    const source = example
      .replaceAll("url(#arrow)", `url(${absolute})`)
      .replace('<use href="#node"/>', `<a href="${new URL("#node", document.URL).href}"><text>Link</text></a>`);
    for (const scope of ["absoluteInline", "absoluteEnlarged"]) {
      const host = document.createElement("div");
      host.innerHTML = prepareMermaidSvg(source, scope);
      const reference = host.querySelector("[marker-end]")!.getAttribute("marker-end")!;
      expect(reference).toBe(`url(#${host.querySelector("marker")!.id})`);
      expect(host.querySelector("a")!.getAttribute("href")).toBe(`#${host.querySelector("g")!.id}`);
    }
  });

  it("rejects invalid renderer output", () => {
    expect(() => prepareMermaidSvg("<div>not a diagram</div>", "bad")).toThrow("Invalid diagram output");
  });

  it("preserves Mermaid's HTML labels while sanitizing their contents", () => {
    const output = prepareMermaidSvg(
      '<svg><foreignObject width="100" height="24"><div xmlns="http://www.w3.org/1999/xhtml"><span>Question</span><script>alert(1)</script><img src="x" onerror="alert(1)"></div></foreignObject></svg>',
      "htmlLabel",
    );
    const host = document.createElement("div");
    host.innerHTML = output;
    expect(host.querySelector("foreignObject")!.textContent).toBe("Question");
    expect(output).not.toMatch(/<script|onerror|alert\(1\)/i);
    expect(host.querySelector("foreignObject")!.getAttribute("width")).toBe("100");
  });
});
