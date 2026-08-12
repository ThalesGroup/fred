// @vitest-environment happy-dom
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

import { afterEach, describe, expect, it, vi } from "vitest";
import { toEmailHtml, toPlainText, writeRichClipboard } from "./clipboardUtils";

function fragment(html: string): HTMLElement {
  const div = document.createElement("div");
  div.innerHTML = html;
  return div;
}

/** Regression guard for #2336: the emitted HTML must never carry anything the
 *  destination document's own styling could be overridden by. */
function assertEmailSafe(html: string) {
  expect(html).not.toMatch(/background/i);
  expect(html).not.toMatch(/color:/i);
  expect(html).not.toMatch(/\bpx\b/);
  expect(html).not.toMatch(/\brem\b/);
  expect(html).not.toMatch(/var\(/);
  expect(html).not.toMatch(/class=/);
  expect(html).not.toMatch(/<h[1-6][ >]/i);
  expect(html).not.toMatch(/<style/i);
  const fontFamilyDeclarations = html.match(/font-family:[^"]*/g) ?? [];
  fontFamilyDeclarations.forEach((decl) => expect(decl).toContain("Consolas"));
}

describe("toEmailHtml", () => {
  it("wraps a plain paragraph and stays email-safe", () => {
    const html = toEmailHtml(fragment("<p>Hello world</p>"));
    assertEmailSafe(html);
    expect(html).toBe('<p style="margin:0 0 10pt">Hello world</p>');
  });

  it("maps heading levels 1-4 to sized strong text, never real heading tags", () => {
    const html = toEmailHtml(fragment("<h1>A</h1><h2>B</h2><h3>C</h3><h4>D</h4>"));
    assertEmailSafe(html);
    expect(html).toContain('font-size:13pt">A</strong>');
    expect(html).toContain('font-size:13pt">B</strong>');
    expect(html).toContain('font-size:12pt">C</strong>');
    expect(html).toContain('font-size:11pt">D</strong>');
  });

  it("preserves nested lists and mixed inline emphasis", () => {
    const html = toEmailHtml(
      fragment("<ul><li><strong>bold</strong> and <em>italic</em><ul><li>nested</li></ul></li></ul>"),
    );
    assertEmailSafe(html);
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
    expect(html).toContain("nested");
  });

  it("strips code block syntax-highlighting spans down to plain escaped text", () => {
    const html = toEmailHtml(fragment('<pre><code><span class="token">if</span> x < 1 && y > 2:</code></pre>'));
    assertEmailSafe(html);
    expect(html).toContain("if x &lt; 1 &amp;&amp; y &gt; 2:");
    expect(html).not.toContain("<span");
  });

  it("renders a table with per-cell borders, since Word ignores table-level borders", () => {
    const html = toEmailHtml(fragment("<table><tr><th>Name</th></tr><tr><td>Alice</td></tr></table>"));
    assertEmailSafe(html);
    expect(html).toContain('<th style="border:1pt solid #cccccc');
    expect(html).toContain('<td style="border:1pt solid #cccccc');
  });

  it("keeps absolute and mailto links, resolves relative links, drops javascript: hrefs", () => {
    const html = toEmailHtml(
      fragment(
        '<a href="https://example.com/x">abs</a>' +
          '<a href="/docs/page">rel</a>' +
          '<a href="mailto:a@b.com">mail</a>' +
          '<a href="javascript:alert(1)">bad</a>',
      ),
    );
    assertEmailSafe(html);
    expect(html).toContain('<a href="https://example.com/x">abs</a>');
    expect(html).toMatch(/<a href="https?:\/\/[^"]*\/docs\/page">rel<\/a>/);
    expect(html).toContain('<a href="mailto:a@b.com">mail</a>');
    expect(html).not.toContain("javascript:");
    expect(html).toContain("bad"); // text survives, just unwrapped — no <a>, no href
  });

  it("drops nodes marked data-clipboard-ignore entirely", () => {
    const html = toEmailHtml(fragment("<p>keep<span data-clipboard-ignore>drop me</span></p>"));
    expect(html).not.toContain("drop me");
    expect(html).toContain("keep");
  });

  it("replaces an SVG diagram with a bracketed alt-text placeholder", () => {
    const withLabel = toEmailHtml(fragment('<svg aria-label="authentication flow"></svg>'));
    expect(withLabel).toBe("[diagram: authentication flow]");
    const withoutLabel = toEmailHtml(fragment("<svg></svg>"));
    expect(withoutLabel).toBe("[diagram]");
  });

  it("returns empty string for an empty or whitespace-only fragment", () => {
    expect(toEmailHtml(fragment(""))).toBe("");
    expect(toEmailHtml(fragment("   \n  "))).toBe("");
  });
});

describe("toPlainText", () => {
  it("renders nested lists with two-space indent per level and correct markers", () => {
    const text = toPlainText(fragment("<ul><li>one<ol><li>nested</li></ol></li><li>two</li></ul>"));
    expect(text).toContain("- one");
    expect(text).toContain("  1. nested");
    expect(text).toContain("- two");
  });

  it("prefixes blockquote lines with '> '", () => {
    const text = toPlainText(fragment("<blockquote>quoted</blockquote>"));
    expect(text).toBe("> quoted");
  });

  it("emits a table as tab-separated values", () => {
    const text = toPlainText(
      fragment("<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>"),
    );
    expect(text.split("\n")).toEqual(["Name\tAge", "Alice\t30"]);
  });

  it("collapses a link to its URL when the label duplicates it, else 'label (url)'", () => {
    const text = toPlainText(
      fragment('<a href="https://example.com">https://example.com</a> and <a href="https://x.com">click here</a>'),
    );
    expect(text).toContain("https://example.com");
    expect(text).not.toContain("https://example.com (https://example.com)");
    expect(text).toContain("click here (https://x.com)");
  });

  it("preserves fenced code verbatim including indentation", () => {
    const text = toPlainText(fragment("<pre><code>  def f():\n      return 1</code></pre>"));
    expect(text).toContain("  def f():\n      return 1");
  });

  it("collapses runs of 3+ blank lines to one", () => {
    const text = toPlainText(fragment("<p>a</p><p></p><p></p><p>b</p>"));
    expect(text).not.toMatch(/\n{3,}/);
  });
});

describe("writeRichClipboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("writes both flavours via the async Clipboard API when available", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    // A real function declaration, not an arrow — ClipboardItem is invoked
    // with `new`, which arrow functions can't support.
    vi.stubGlobal("ClipboardItem", function ClipboardItem(items: unknown) {
      return items;
    });
    vi.stubGlobal("navigator", { clipboard: { write, writeText: vi.fn() } });

    const ok = await writeRichClipboard("<p>hi</p>", "hi");
    expect(ok).toBe(true);
    expect(write).toHaveBeenCalledTimes(1);
  });

  it("falls back to writeText when ClipboardItem is unavailable", async () => {
    vi.stubGlobal("ClipboardItem", undefined);
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    const ok = await writeRichClipboard("<p>hi</p>", "hi");
    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hi");
  });

  it("returns false, never throws, when every write path rejects", async () => {
    vi.stubGlobal("ClipboardItem", undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });

    await expect(writeRichClipboard("<p>hi</p>", "hi")).resolves.toBe(false);
  });
});
