import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ContextPromptChips } from "./ContextPromptChips";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
}));

function makePrompt(
  over: Partial<ContextPromptSummary> & Pick<ContextPromptSummary, "id" | "name" | "scope">,
): ContextPromptSummary {
  return { version: 1, session_count: 0, ...over } as ContextPromptSummary;
}

function render(prompts: ContextPromptSummary[]): string {
  return renderToStaticMarkup(<ContextPromptChips prompts={prompts} onRemove={() => undefined} />);
}

describe("ContextPromptChips", () => {
  it("renders nothing when no prompt is attached", () => {
    expect(render([])).toBe("");
  });

  it("renders one removable pill per attached prompt", () => {
    const html = render([
      makePrompt({ id: "p1", name: "Bid analysis", scope: "personal" }),
      makePrompt({ id: "p2", name: "Reply in French", scope: "team" }),
    ]);
    expect(html).toContain("Bid analysis");
    expect(html).toContain("Reply in French");
    // one remove <button> per pill
    expect(html.match(/<button/g)?.length).toBe(2);
  });

  it("uses the category icon, falling back to edit_note when unset", () => {
    expect(render([makePrompt({ id: "p1", name: "A", scope: "team", category: "summary" })])).toContain(
      'data-icon="summarize"',
    );
    expect(render([makePrompt({ id: "p1", name: "A", scope: "team", category: null })])).toContain(
      'data-icon="edit_note"',
    );
  });
});
