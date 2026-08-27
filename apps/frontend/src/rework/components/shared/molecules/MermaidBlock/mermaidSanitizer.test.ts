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

  it("resolves a bare multi-word reference to the node declared with that label", () => {
    const code = [
      "flowchart TD",
      "BackendPython --> LLMAzure[LLM Azure]",
      "OpenSearch -->|Recherche sémantique| LLM Azure",
      "LLM Azure -->|Réponse filtrée| BackendPython",
    ].join("\n");
    const sanitized = sanitizeMermaidForParsing(code);
    expect(sanitized).toContain("OpenSearch -->|Recherche sémantique| LLMAzure");
    expect(sanitized).toContain("LLMAzure -->|Réponse filtrée| BackendPython");
    expect(sanitized).not.toContain("LLM_Azure");
  });

  it("generates a safe ID with quoted label when no declaration matches", () => {
    const code = "flowchart TD\nA --> LLM Azure --> C";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> LLM_Azure["LLM Azure"] --> C');
  });

  it("derives ASCII-safe IDs from accented labels", () => {
    const code = "flowchart TD\nA --> Base de données";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> Base_de_donnees["Base de données"]');
  });

  it("repairs NFD-normalized input the same as NFC input", () => {
    const code = "flowchart TD\nA --> Base de données".normalize("NFD");
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> Base_de_donnees["Base de données"]');
  });

  it("keeps non-Latin labels distinct instead of collapsing their IDs", () => {
    const code = "flowchart TD\nA --> Привет мир\nB --> Другой узел";
    const sanitized = sanitizeMermaidForParsing(code);
    expect(sanitized).toContain('A --> Привет_мир["Привет мир"]');
    expect(sanitized).toContain('B --> Другои_узел["Другой узел"]');
  });

  it("does not relabel a declared node whose ID collides with the derived one", () => {
    const code = "flowchart TD\nLLM_Azure[Other Thing]\nA --> LLM Azure";
    const sanitized = sanitizeMermaidForParsing(code);
    expect(sanitized).toContain("LLM_Azure[Other Thing]");
    expect(sanitized).toContain('A --> LLM_Azure_["LLM Azure"]');
  });

  it("still repairs flowcharts that open with YAML frontmatter", () => {
    const code = "---\ntitle: Archi\n---\nflowchart TD\nA --> LLM Azure";
    const sanitized = sanitizeMermaidForParsing(code);
    expect(sanitized).toContain("---\ntitle: Archi\n---");
    expect(sanitized).toContain('A --> LLM_Azure["LLM Azure"]');
  });

  it("repairs a bare reference on a semicolon-terminated statement", () => {
    const code = "flowchart TD\nA --> LLM Azure;";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> LLM_Azure["LLM Azure"];');
  });

  it("repairs a bare reference after the & endpoint separator", () => {
    const code = "flowchart TD\nA --> B & LLM Azure";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nA --> B & LLM_Azure["LLM Azure"]');
  });

  it("repairs around circle and cross edge decorations without corrupting them", () => {
    const circle = "flowchart TD\nA ---o LLM Azure";
    expect(sanitizeMermaidForParsing(circle)).toBe('flowchart TD\nA ---o LLM_Azure["LLM Azure"]');
    const cross = "flowchart TD\nLLM Azure x--x B";
    expect(sanitizeMermaidForParsing(cross)).toBe('flowchart TD\nLLM_Azure["LLM Azure"] x--x B');
  });

  it("repairs around a dotted bidirectional arrow", () => {
    const code = "flowchart TD\nLLM Azure <-.-> B";
    expect(sanitizeMermaidForParsing(code)).toBe('flowchart TD\nLLM_Azure["LLM Azure"] <-.-> B');
  });

  it("leaves open edge-text syntax untouched", () => {
    const code = "flowchart TD\nA -- some text --> B";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });

  it("does not split edge-token lookalikes inside a bracket label", () => {
    const code = "flowchart TD\nA[raw data --> clean data] --> B";
    expect(sanitizeMermaidForParsing(code)).toBe(code);
  });

  it("leaves keyword-led lines untouched", () => {
    const code = "flowchart TD\nsubgraph Flux principal --> secondaire\nA --> B\nend";
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

  it("handles many leading blank lines without pathological backtracking", () => {
    const code = "\n".repeat(64) + "sequenceDiagram\nAlice-->>Bob: hi";
    const start = performance.now();
    expect(sanitizeMermaidForParsing(code)).toBe(code);
    expect(performance.now() - start).toBeLessThan(200);
  });
});
