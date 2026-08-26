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

  it("rewrites bare multi-word node references to a safe ID with quoted label", () => {
    const code = [
      "flowchart TD",
      "BackendPython --> LLMAzure[LLM Azure]",
      "OpenSearch -->|Recherche sémantique| LLM Azure",
      "LLM Azure -->|Réponse filtrée| BackendPython",
    ].join("\n");
    const sanitized = sanitizeMermaidForParsing(code);
    expect(sanitized).toContain('OpenSearch -->|Recherche sémantique| LLM_Azure["LLM Azure"]');
    expect(sanitized).toContain('LLM_Azure["LLM Azure"] -->|Réponse filtrée| BackendPython');
  });

  it("rewrites a bare multi-word reference in the middle of an edge chain", () => {
    const code = "flowchart TD\nA --> LLM Azure --> C";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> LLM_Azure["LLM Azure"] --> C');
  });

  it("derives ASCII-safe IDs from accented labels", () => {
    const code = "flowchart TD\nA --> Base de données";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> Base_de_donnees["Base de données"]');
  });

  it("leaves open edge-text syntax untouched", () => {
    const code = "flowchart TD\nA -- some text --> B";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });

  it("leaves single-word endpoints untouched", () => {
    const code = "flowchart TD\nOpenSearch -->|Recherche| LLMAzure";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });

  it("does not touch non-flowchart diagrams", () => {
    const code = "sequenceDiagram\nAlice --> Bob Builder";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });
});
