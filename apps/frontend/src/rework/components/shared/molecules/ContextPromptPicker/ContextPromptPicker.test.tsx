import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ContextPromptPicker } from "./ContextPromptPicker";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type, filled }: { type: string; filled?: boolean }) => (
    <i data-icon={type} data-filled={filled ? "true" : "false"} />
  ),
}));

function makePrompt(
  over: Partial<ContextPromptSummary> & Pick<ContextPromptSummary, "id" | "name" | "scope">,
): ContextPromptSummary {
  return { version: 1, session_count: 0, ...over } as ContextPromptSummary;
}

function render(prompts: ContextPromptSummary[]): string {
  return renderToStaticMarkup(<ContextPromptPicker prompts={prompts} onSelect={() => undefined} />);
}

function countMatches(html: string, needle: RegExp): number {
  return html.match(needle)?.length ?? 0;
}

describe("ContextPromptPicker", () => {
  it("renders the empty state when no prompts are available", () => {
    expect(render([])).toContain("chatbot.contextPrompts.empty");
  });

  it("orders personal prompts before team prompts, with no scope labels", () => {
    const html = render([
      makePrompt({ id: "t1", name: "Team one", scope: "team" }),
      makePrompt({ id: "p1", name: "Personal one", scope: "personal" }),
    ]);
    const personal = html.indexOf("Personal one");
    const team = html.indexOf("Team one");
    expect(personal).toBeGreaterThanOrEqual(0);
    expect(personal).toBeLessThan(team);
    // Scope group labels were removed — the parent menu row already says "Team prompts".
    expect(html).not.toContain("chatbot.contextPrompts.scope");
  });

  it("renders one action row per prompt with no selection checkbox", () => {
    const html = render([
      makePrompt({ id: "p1", name: "A", scope: "personal" }),
      makePrompt({ id: "p2", name: "B", scope: "personal" }),
    ]);
    expect(countMatches(html, /role="menuitem"/g)).toBe(2);
    // Insert-on-click rows are actions, not toggles — no checkbox affordance.
    expect(html).not.toContain('data-icon="check_box"');
    expect(html).not.toContain('data-icon="check_box_outline_blank"');
    expect(html).not.toContain("data-selected");
  });

  it("renders no leading icon and no usage count on rows", () => {
    const html = render([makePrompt({ id: "p1", name: "A", scope: "personal", session_count: 7 })]);
    expect(html).not.toContain('data-icon="edit_note"');
    expect(html).not.toContain("chatbot.contextPrompts.uses");
  });

  it("renders five stars with the rounded score filled, and none when score is null", () => {
    const scored = render([makePrompt({ id: "p1", name: "A", scope: "team", score: 3 })]);
    expect(countMatches(scored, /data-icon="star"/g)).toBe(5);
    expect(countMatches(scored, /data-icon="star" data-filled="true"/g)).toBe(3);

    const unscored = render([makePrompt({ id: "p1", name: "A", scope: "team", score: null })]);
    expect(unscored).not.toContain('data-icon="star"');
  });
});
