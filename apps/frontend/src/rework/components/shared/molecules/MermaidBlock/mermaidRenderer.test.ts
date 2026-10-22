// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderMermaid, type MermaidTheme } from "./mermaidRenderer";
import { prepareMermaidSvg } from "./mermaidSvg";

const official = vi.hoisted(() => ({ initialize: vi.fn(), render: vi.fn() }));
vi.mock("mermaid", () => ({ default: official }));

const theme: MermaidTheme = {
  colors: {
    bg: "#ffffff",
    fg: "#191c1f",
    accent: "#00658c",
    line: "#5a5f63",
    muted: "#5a5f63",
    surface: "#f3f9fd",
    border: "#c1c7cb",
  },
  font: "Inter",
  dark: false,
  secondary: "#64597c",
  tertiary: "#805239",
};

const diagramExamples = [
  {
    name: "flowchart",
    code: "flowchart LR\n Q[Question] --> A[Agent]\n A --> D[Documents]\n A --> W[Web]\n D --> R[Réponse]\n W --> R",
    labels: ["Question", "Agent", "Documents", "Web", "Réponse"],
  },
  {
    name: "sequence",
    code: "sequenceDiagram\n participant U as Utilisateur\n participant A as Agent\n U->>A: Question\n A-->>U: Réponse",
    labels: ["Utilisateur", "Agent", "Question", "Réponse"],
  },
  {
    name: "state",
    code: "stateDiagram-v2\n [*] --> Idle\n Idle --> Active: Start\n Active --> [*]",
    labels: ["Idle", "Active", "Start"],
  },
  {
    name: "class",
    code: "classDiagram\n class Agent {\n +String name\n +answer()\n }\n Agent --> Source : reads",
    labels: ["Agent", "Source", "name", "answer", "reads"],
  },
  {
    name: "ER",
    code: "erDiagram\n TEAM ||--o{ AGENT : owns\n TEAM {\n string id PK\n }",
    labels: ["TEAM", "AGENT", "owns", "id"],
  },
  {
    name: "XY",
    code: 'xychart-beta\n title "Requests"\n x-axis [Jan, Feb, Mar]\n y-axis "Count" 0 --> 30\n bar [10, 20, 15]\n line [15, 12, 25]',
    labels: ["Requests", "Jan", "Feb", "Mar", "Count"],
  },
];

beforeEach(() => {
  official.initialize.mockReset();
  official.render
    .mockReset()
    .mockImplementation(async (id: string) => ({ svg: `<svg id="${id}"><text>Compatibility</text></svg>` }));
});

describe("preferred Mermaid rendering", () => {
  it.each(diagramExamples)("preserves the labels of a real $name diagram", async ({ code, labels }) => {
    const raw = await renderMermaid(code, "example", theme);
    const container = document.createElement("div");
    container.innerHTML = prepareMermaidSvg(raw, "exampleInline");
    for (const label of labels) expect(container.textContent).toContain(label);
    expect(official.render).not.toHaveBeenCalled();
    expect(container.innerHTML).not.toContain("fonts.googleapis.com");
    expect(container.innerHTML).toContain("var(--on-surface)");
  });

  it("uses Fred tokens for every XY series instead of the library's fallback palette", async () => {
    const raw = await renderMermaid(diagramExamples[5].code, "chart", theme);
    const svg = prepareMermaidSvg(raw, "chartInline");
    expect(svg).toContain("--xychart-color-0:var(--primary)");
    expect(svg).toContain("--xychart-color-1:var(--secondary)");
  });

  it("keeps marker references distinct from a node named arrowhead", async () => {
    const raw = await renderMermaid("flowchart LR\n arrowhead[Marker node] --> B[Other]", "collision", theme);
    const container = document.createElement("div");
    container.innerHTML = prepareMermaidSvg(raw, "collisionInline");
    const id = container
      .querySelector("[marker-end]")!
      .getAttribute("marker-end")!
      .match(/#([^)'"\s]+)/)![1];
    expect(container.querySelector(`[id="${id}"]`)!.localName).toBe("marker");
    expect(container.textContent).toContain("Marker node");
  });
});

describe("Mermaid compatibility", () => {
  it.each([
    "graph TD; A-->B",
    'pie title Budget\n "Tools" : 42\n "Other" : 58',
    "gantt\n title Delivery\n dateFormat YYYY-MM-DD\n Implementation :2026-10-22, 3d",
    "sequenceDiagram\n A->>B: Start\n activate B\n B-->>A: Done\n deactivate B",
    'flowchart TD\n A@{ shape: cloud, label: "Cloud" } --> B',
    "stateDiagram-v2\n A --> B\n note right of A : Important",
    "---\ntitle: Diagram\n---\nflowchart TD\n A --> B",
    "flowchart LR\n A --> B\n A[Question]\n B[Answer]",
    "flowchart LR\n A[First] --> B\n A[Revised]",
    'stateDiagram-v2\n A --> B\n state "Question" as A',
    'stateDiagram-v2\n state "First" as A\n state "Revised" as A\n A --> B',
    "erDiagram\n AGENT }o--|| TEAM : belongs",
    "erDiagram\n AGENT {\n string id PK, FK\n }",
    "erDiagram\n AGENT {\n string id PK,FK\n }",
    "sequenceDiagram\n A->>B: Question\n participant A as Alice\n participant B as Bob",
    "sequenceDiagram\n participant A as First\n participant A as Revised\n A->>B: Question",
  ])("preserves unsupported source through the official renderer: %s", async (code) => {
    await renderMermaid(code, "fallback", theme);
    expect(official.render).toHaveBeenCalledWith("fallbackRaw", code);
    expect(official.initialize).toHaveBeenCalledWith(
      expect.objectContaining({
        theme: "base",
        securityLevel: "strict",
        themeVariables: expect.objectContaining({ primaryTextColor: theme.colors.fg, background: theme.colors.bg }),
      }),
    );
  });

  it("tries raw source before the existing repair and cleans Mermaid's temporary DOM", async () => {
    const code = "flowchart TD\n A[Web App (Europe)] --> LLM Azure";
    official.render.mockImplementationOnce(async (id: string) => {
      const leftover = document.createElement("div");
      leftover.id = `d${id}`;
      document.body.append(leftover);
      throw new Error("Syntax error");
    });
    const output = await renderMermaid(code, "repair", theme);
    expect(official.render.mock.calls[0][1]).toBe(code);
    expect(output).toContain("<svg");
    expect(document.getElementById("drepairRaw")).toBeNull();
    expect(official.render.mock.calls[1]?.[1] ?? output).not.toBe(code);
  });

  it("reports invalid source and still renders the next diagram", async () => {
    official.render.mockRejectedValueOnce(new Error("Syntax error"));
    await expect(renderMermaid("invalid input", "bad", theme)).rejects.toThrow("Syntax error");
    await expect(renderMermaid('pie\n "A": 1', "good", theme)).resolves.toContain("Compatibility");
  });

  it("serializes Mermaid's global theme changes with each corresponding render", async () => {
    let finish!: () => void;
    official.render.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve({ svg: "first" });
        }),
    );
    const first = renderMermaid('pie\n "A": 1', "first", theme);
    const second = renderMermaid('pie\n "A": 1', "second", { ...theme, dark: true });
    await vi.waitFor(() => expect(official.render).toHaveBeenCalledTimes(1));
    expect(official.initialize).toHaveBeenCalledTimes(1);
    finish();
    await Promise.all([first, second]);
    expect(official.initialize.mock.calls[1][0].themeVariables.darkMode).toBe(true);
  });
});
