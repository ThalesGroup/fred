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

// The panel owns two things worth pinning: which space's prompts it shows
// (a team chat can reach the caller's personal prompts, a personal chat has no
// team side), and that a failed insert does not dismiss the list.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  promptsByTeam: {} as Record<string, unknown[]>,
  categoriesByTeam: {} as Record<string, unknown[]>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: (
    arg: { teamId: string },
    opts: { skip?: boolean },
  ) => ({ data: opts.skip ? undefined : (h.promptsByTeam[arg.teamId] ?? []), isLoading: false }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: (
    arg: { teamId: string },
    opts: { skip?: boolean },
  ) => ({ data: opts.skip ? undefined : (h.categoriesByTeam[arg.teamId] ?? []) }),
}));

import PromptSelectionChatPanel from "./PromptSelectionChatPanel.tsx";

const TEAM_ID = "team-1";
const PERSONAL_ID = "personal-u1";

function prompt(over: Partial<ContextPromptSummary> & Pick<ContextPromptSummary, "id" | "name">) {
  return { scope: "team", version: 1, session_count: 0, ...over } as ContextPromptSummary;
}

let container: HTMLDivElement;
let root: Root;

function mount(props: Partial<React.ComponentProps<typeof PromptSelectionChatPanel>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <PromptSelectionChatPanel
        open
        onClose={props.onClose ?? (() => {})}
        teamId={TEAM_ID}
        personalTeamId={PERSONAL_ID}
        isPersonalChat={props.isPersonalChat ?? false}
        onInsert={props.onInsert ?? (async () => true)}
      />,
    );
  });
}

function buttonWithText(text: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes(text));
}

async function click(el: Element | undefined) {
  await act(async () => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

beforeEach(() => {
  h.promptsByTeam = {
    [TEAM_ID]: [
      prompt({ id: "t1", name: "Weekly report", description: "Sprint summary", category_id: "cat-a" }),
      prompt({ id: "t2", name: "Bug triage", category_id: null }),
    ],
    [PERSONAL_ID]: [prompt({ id: "p1", name: "My scratch prompt", scope: "personal" })],
  };
  h.categoriesByTeam = { [TEAM_ID]: [{ id: "cat-a", name: "Reports" }], [PERSONAL_ID]: [] };
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PromptSelectionChatPanel", () => {
  it("opens on the team space in a team chat", () => {
    mount();
    expect(container.textContent).toContain("Weekly report");
    expect(container.textContent).not.toContain("My scratch prompt");
  });

  it("switching to the personal space lists the caller's own prompts", async () => {
    // The team call never returns personal prompts, so this is a second query.
    mount();
    await click(buttonWithText("chatbot.promptSelectionPanel.space.personal"));

    expect(container.textContent).toContain("My scratch prompt");
    expect(container.textContent).not.toContain("Weekly report");
  });

  it("hides the space picker in a personal chat", () => {
    // The team side would have nothing to offer.
    mount({ isPersonalChat: true });

    expect(container.textContent).not.toContain("chatbot.promptSelectionPanel.space.team");
  });

  it("filters the list as the user searches", async () => {
    mount();
    const input = container.querySelector("input") as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, "triage");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(container.textContent).toContain("Bug triage");
    expect(container.textContent).not.toContain("Weekly report");
  });

  it("says the space is empty when it holds no prompt at all", () => {
    h.promptsByTeam[TEAM_ID] = [];
    mount();
    // Exact text, not a substring: "…empty" is a prefix of "…emptyFilters", so
    // `toContain` cannot tell the two messages apart.
    expect(container.querySelector("p")?.textContent).toBe("chatbot.promptSelectionPanel.empty");
  });

  it("says the filters match nothing when the space does hold prompts", async () => {
    // Two different messages: "this space is empty" is not the same problem as
    // "your query excluded everything", and only the second is the user's to fix.
    mount();
    const input = container.querySelector("input") as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, "nothing matches this");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(container.querySelector("p")?.textContent).toBe("chatbot.promptSelectionPanel.emptyFilters");
  });

  it("closes only once the insert resolves", async () => {
    const onClose = vi.fn();
    let release: (ok: boolean) => void = () => {};
    const onInsert = vi.fn(() => new Promise<boolean>((resolve) => (release = resolve)));
    mount({ onClose, onInsert });

    await click(buttonWithText("Weekly report"));
    // In flight: the text is not in the composer yet, so the panel stays.
    expect(onInsert).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => release(true));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open when the insert fails", async () => {
    // The fetch can fail; dismissing the list would lose the user's place.
    const onClose = vi.fn();
    mount({ onClose, onInsert: async () => false });

    await click(buttonWithText("Weekly report"));
    expect(onClose).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Weekly report");
  });

  it("ignores a second pick while one insert is in flight", async () => {
    const onInsert = vi.fn(() => new Promise<boolean>(() => {}));
    mount({ onInsert });

    await click(buttonWithText("Weekly report"));
    await click(buttonWithText("Bug triage"));
    expect(onInsert).toHaveBeenCalledTimes(1);
  });
});
