import { describe, it, expect } from "vitest";
import { getStreamingMarkdownState, streamingGuard } from "./streamingGuard";

describe("streamingGuard — no-op cases", () => {
  it("passes through plain prose", () => {
    expect(streamingGuard("Hello **world**")).toBe("Hello **world**");
  });

  it("passes through empty string", () => {
    expect(streamingGuard("")).toBe("");
  });

  it("passes through a complete backtick fence", () => {
    const text = "Before\n```python\nprint(1)\n```\nAfter";
    expect(streamingGuard(text)).toBe(text);
  });

  it("passes through a complete $$ block", () => {
    const text = "Before\n$$\nx = 1\n$$\nAfter";
    expect(streamingGuard(text)).toBe(text);
  });

  it("passes through a complete :::details block", () => {
    const text = "Before\n:::details[Notes]\ncontent\n:::\nAfter";
    expect(streamingGuard(text)).toBe(text);
  });
});

describe("streamingGuard — truncation cases", () => {
  it("strips an unclosed mermaid fence", () => {
    const text = "Before\n```mermaid\ngraph TD\n    A --> B\n";
    expect(streamingGuard(text)).toBe("Before\n");
  });

  it("strips an unclosed python fence", () => {
    const text = "Before\n```python\nprint(1)\n";
    expect(streamingGuard(text)).toBe("Before\n");
  });

  it("strips only the last open fence and leaves the closed one intact", () => {
    const closed = "```python\nprint(1)\n```\n";
    const open = "```mermaid\ngraph TD\n";
    expect(streamingGuard(closed + open)).toBe(closed);
  });

  it("strips an unclosed $$ block", () => {
    const text = "Prose\n$$\nx = \\frac{1}{2}\n";
    expect(streamingGuard(text)).toBe("Prose\n");
  });

  it("strips an unclosed :::details block", () => {
    const text = "Prose\n:::details[Notes]\nsome content\n";
    expect(streamingGuard(text)).toBe("Prose\n");
  });

  it("returns empty string when the opener is the entire input", () => {
    expect(streamingGuard("```mermaid\n")).toBe("");
  });

  it("returns empty string when only the open delimiter is present", () => {
    expect(streamingGuard("```mermaid")).toBe("");
  });
});

describe("streamingGuard — false-positive guards", () => {
  it("does not confuse inner fence-like text inside a complete outer fence", () => {
    // The python block contains ```mermaid as documentation — must not be treated
    // as a nested opener per CommonMark §4.5 rule 2.
    const text = "```python\n# how to write mermaid:\n```mermaid\nA-->B\n```\nAfter";
    expect(streamingGuard(text)).toBe(text);
  });

  it("does not treat triple backticks mid-line as an opener", () => {
    // Inline code containing ``` is never at column 0 as a standalone fence.
    const text = "Use ` ``` ` to open a fence.\n";
    expect(streamingGuard(text)).toBe(text);
  });

  it("does not treat a 4-space-indented fence as an opener (code block via indentation)", () => {
    const text = "    ```python\nprint(1)\n";
    expect(streamingGuard(text)).toBe(text);
  });
});

describe("getStreamingMarkdownState", () => {
  it("returns a pending mermaid fence for source-first streaming previews", () => {
    const text = "Before\n```mermaid\ngraph TD\n    A --> B\n";

    expect(getStreamingMarkdownState(text)).toEqual({
      stableMarkdown: "Before\n",
      pendingFence: {
        kind: "code",
        language: "mermaid",
        content: "graph TD\n    A --> B\n",
      },
    });
  });

  it("returns no pending fence once the mermaid block is complete", () => {
    const text = "Before\n```mermaid\ngraph TD\n    A --> B\n```\nAfter";

    expect(getStreamingMarkdownState(text)).toEqual({
      stableMarkdown: text,
      pendingFence: null,
    });
  });
});
