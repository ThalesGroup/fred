import { describe, expect, it } from "vitest";
import { sanitizeMermaidForParsing } from "./mermaidSanitizer";

describe("sanitizeMermaidForParsing", () => {
  it("normalizes literal backslash-n to <br/>", () => {
    const code = "flowchart TD\nA[Line1\\nLine2] --> B";
    expect(sanitizeMermaidForParsing(code)).toContain("Line1<br/>Line2");
  });

  it("quotes bracket labels that contain <br/> and parentheses", () => {
    const code = "flowchart TD\nC1[Web App\\n(Europe)] --> LB1";
    expect(sanitizeMermaidForParsing(code)).toContain('C1["Web App<br/>(Europe)"]');
  });

  it("keeps already quoted labels unchanged", () => {
    const code = 'flowchart TD\nC1["Web App<br/>(Europe)"] --> LB1';
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });

  it("does not quote simple labels that do not need it", () => {
    const code = "flowchart TD\nA[SimpleLabel] --> B";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });
});
