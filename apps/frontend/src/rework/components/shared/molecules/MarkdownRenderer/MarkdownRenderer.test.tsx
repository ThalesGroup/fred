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

// Coverage centres on block-vs-inline routing: a fence is a block whether or
// not it carries a language, and only backtick spans reach the inline path.
// The block renderers are stubbed so the test exercises the routing alone.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarkdownRenderer } from "./MarkdownRenderer";
import styles from "./MarkdownRenderer.module.css";

vi.mock("../CodeBlock/CodeBlock", () => ({
  CodeBlock: ({ code, language, inline }: { code: string; language?: string; inline?: boolean }) => (
    <span data-code-block data-inline={inline ? "1" : "0"} data-language={language ?? ""}>
      {code}
    </span>
  ),
}));

vi.mock("../MermaidBlock/MermaidBlock", () => ({
  MermaidBlock: ({ code }: { code: string }) => <span data-mermaid-block>{code}</span>,
}));

vi.mock("../MindMapBlock", () => ({
  MindMapBlock: ({ code, language }: { code: string; language: string }) => (
    <span data-mindmap-block data-language={language}>
      {code}
    </span>
  ),
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(text: string) {
  act(() => root.render(<MarkdownRenderer text={text} />));
}

const codeBlocks = () => Array.from(container.querySelectorAll<HTMLElement>("[data-code-block]"));

describe("MarkdownRenderer layout variants", () => {
  it.each([false, true])("keeps announcement text inline with compact=%s", (compact) => {
    act(() => root.render(<MarkdownRenderer text="Read **this announcement**" inline compact={compact} />));
    const wrapper = container.querySelector("[data-copyable-content]");
    expect(wrapper?.tagName).toBe("SPAN");
    expect(wrapper?.querySelector("p")).toBeNull();
    expect(wrapper?.querySelector("strong")?.textContent).toBe("this announcement");
    expect(wrapper?.classList.contains(styles.inline)).toBe(true);
    expect(wrapper?.classList.contains(styles.compact)).toBe(compact);
  });

  it("keeps compact full-width catalogs as block content", () => {
    act(() => root.render(<MarkdownRenderer text={"## Catalog\n\nTable description"} compact fullWidth />));
    const wrapper = container.querySelector("[data-copyable-content]");
    expect(wrapper?.tagName).toBe("DIV");
    expect(wrapper?.querySelector("h2")?.textContent).toBe("Catalog");
    expect(wrapper?.querySelector("p")?.textContent).toBe("Table description");
    expect(wrapper?.classList.contains(styles.compact)).toBe(true);
    expect(wrapper?.classList.contains(styles.fullWidth)).toBe(true);
  });
});

describe("MarkdownRenderer code routing", () => {
  it("renders a fence without a language as a plaintext block", () => {
    render("répète :\n```\nAAA\nBBB\n```\n");
    const [block] = codeBlocks();
    expect(block).toBeDefined();
    expect(block.dataset.inline).toBe("0");
    expect(block.dataset.language).toBe("");
    expect(block.textContent).toBe("AAA\nBBB");
    expect(container.querySelector("pre")).toBeNull();
  });

  it("renders a fence with a language as a block carrying that language", () => {
    render("```python\nprint(1)\n```\n");
    const [block] = codeBlocks();
    expect(block.dataset.inline).toBe("0");
    expect(block.dataset.language).toBe("python");
    expect(block.textContent).toBe("print(1)");
  });

  it("renders an indented code block as a block", () => {
    render("Texte :\n\n    AAA\n    BBB\n");
    const [block] = codeBlocks();
    expect(block.dataset.inline).toBe("0");
    expect(block.textContent).toBe("AAA\nBBB");
  });

  it("renders a backtick span as inline code", () => {
    render("appelle `foo()` puis continue");
    const [inline] = codeBlocks();
    expect(inline.dataset.inline).toBe("1");
    expect(inline.textContent).toBe("foo()");
  });

  it("routes mermaid and mindmap fences to their dedicated blocks", () => {
    render("```mermaid\ngraph TD; A-->B\n```\n\n```mindmap\nroot\n```\n");
    expect(container.querySelector("[data-mermaid-block]")?.textContent).toBe("graph TD; A-->B");
    const mindmap = container.querySelector<HTMLElement>("[data-mindmap-block]");
    expect(mindmap?.dataset.language).toBe("mindmap");
    expect(codeBlocks()).toHaveLength(0);
  });
});
