import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ContextPromptPicker, nextContextPromptSelection } from "./ContextPromptPicker";

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

function render(prompts: ContextPromptSummary[], selectedIds: string[]): string {
  return renderToStaticMarkup(
    <ContextPromptPicker prompts={prompts} selectedIds={selectedIds} onChange={() => undefined} />,
  );
}

function countMatches(html: string, needle: RegExp): number {
  return html.match(needle)?.length ?? 0;
}

describe("ContextPromptPicker", () => {
  it("renders the empty state when no prompts are available", () => {
    const html = render([], []);
    expect(html).toContain("chatbot.contextPrompts.empty");
    expect(html).not.toContain("data-selected");
  });

  it("renders scope groups in order personal → team → default", () => {
    const html = render(
      [
        makePrompt({ id: "d1", name: "Default one", scope: "default" }),
        makePrompt({ id: "t1", name: "Team one", scope: "team" }),
        makePrompt({ id: "p1", name: "Personal one", scope: "personal" }),
      ],
      [],
    );
    const personal = html.indexOf("chatbot.contextPrompts.scope.personal");
    const team = html.indexOf("chatbot.contextPrompts.scope.team");
    const def = html.indexOf("chatbot.contextPrompts.scope.default");
    expect(personal).toBeGreaterThanOrEqual(0);
    expect(personal).toBeLessThan(team);
    expect(team).toBeLessThan(def);
    expect(html).toContain("Personal one");
    expect(html).toContain("Team one");
    expect(html).toContain("Default one");
  });

  it("marks selected rows and toggles the checkbox icon", () => {
    const html = render(
      [makePrompt({ id: "p1", name: "A", scope: "personal" }), makePrompt({ id: "p2", name: "B", scope: "personal" })],
      ["p1"],
    );
    expect(html).toContain('data-selected="true"');
    expect(html).toContain('data-icon="check_box"');
    expect(html).toContain('data-icon="check_box_outline_blank"');
  });

  it("renders five stars with the rounded score filled, and none when score is null", () => {
    const scored = render([makePrompt({ id: "p1", name: "A", scope: "team", score: 3 })], []);
    expect(countMatches(scored, /data-icon="star"/g)).toBe(5);
    expect(countMatches(scored, /data-icon="star" data-filled="true"/g)).toBe(3);

    const unscored = render([makePrompt({ id: "p1", name: "A", scope: "team", score: null })], []);
    expect(unscored).not.toContain('data-icon="star"');
  });

  it("uses the category icon, falling back to edit_note when unset", () => {
    const withCategory = render([makePrompt({ id: "p1", name: "A", scope: "personal", category: "summary" })], []);
    expect(withCategory).toContain('data-icon="summarize"');

    const withoutCategory = render([makePrompt({ id: "p1", name: "A", scope: "personal", category: null })], []);
    expect(withoutCategory).toContain('data-icon="edit_note"');
  });
});

describe("nextContextPromptSelection", () => {
  it("appends a new id at the end, preserving order", () => {
    expect(nextContextPromptSelection([], "a")).toEqual(["a"]);
    expect(nextContextPromptSelection(["a"], "b")).toEqual(["a", "b"]);
    expect(nextContextPromptSelection(["b"], "a")).toEqual(["b", "a"]);
  });

  it("removes an already-selected id without disturbing the rest", () => {
    expect(nextContextPromptSelection(["a", "b", "c"], "b")).toEqual(["a", "c"]);
    expect(nextContextPromptSelection(["a"], "a")).toEqual([]);
  });
});
