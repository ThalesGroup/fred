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
import type { PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { promptSummaryFixture } from "../../../pages/PromptsPage/weaverPromptFixtures";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  promptsByTeam: {} as Record<string, PromptSummary[]>,
  isError: false,
  pending: false,
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePromptCatalogQuery: ({ spaceId }: { spaceId: string }, { skip }: { skip?: boolean }) => ({
    currentData: skip || h.pending ? undefined : { items: h.promptsByTeam[spaceId] ?? [], next_cursor: null },
    isFetching: !skip && h.pending,
    isError: !skip && h.isError,
    refetch: h.refetch,
  }),
}));

import PromptSelectionChatPanel from "./PromptSelectionChatPanel.tsx";

const TEAM_ID = "team-1";
const PERSONAL_ID = "personal-u1";

let container: HTMLDivElement;
let root: Root;

function mount(props: Partial<React.ComponentProps<typeof PromptSelectionChatPanel>> = {}) {
  if (!container) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  }
  act(() => {
    root.render(
      <PromptSelectionChatPanel
        open={props.open ?? true}
        onClose={props.onClose ?? (() => {})}
        teamId={props.teamId ?? TEAM_ID}
        personalTeamId={"personalTeamId" in props ? props.personalTeamId : PERSONAL_ID}
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
      promptSummaryFixture({
        prompt_id: "t1",
        space_id: TEAM_ID,
        display_name: "Weekly report",
        description: "Sprint summary",
      }),
      promptSummaryFixture({ prompt_id: "t2", space_id: TEAM_ID, display_name: "Bug triage", logical_name: "triage" }),
    ],
    [PERSONAL_ID]: [
      promptSummaryFixture({ prompt_id: "p1", space_id: PERSONAL_ID, display_name: "My scratch prompt" }),
    ],
  };
  h.isError = false;
  h.pending = false;
  h.refetch.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  container = undefined!;
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

  it("hides the space picker until the personal id resolves", () => {
    // Bootstrap may not have answered yet. Offering "My space" then would open
    // a tab whose query is skipped and whose spinner could never clear.
    mount({ personalTeamId: undefined });

    expect(container.textContent).not.toContain("chatbot.promptSelectionPanel.space.personal");
    expect(container.textContent).toContain("Weekly report");
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
    expect(Array.from(container.querySelectorAll("p")).slice(-1)[0]?.textContent).toBe(
      "chatbot.promptSelectionPanel.empty",
    );
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

    expect(Array.from(container.querySelectorAll("p")).slice(-1)[0]?.textContent).toBe(
      "chatbot.promptSelectionPanel.emptyFilters",
    );
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

  it("shows a catalog error and retries instead of presenting cached rows as complete", async () => {
    h.isError = true;
    mount();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(buttonWithText("Weekly report")).toBeUndefined();
    await click(buttonWithText("rework.weaverPrompts.retry"));
    expect(h.refetch).toHaveBeenCalledOnce();
  });

  it.each([false, true])("ignores an old insertion after reopening (new insertion: %s)", async (again) => {
    const onClose = vi.fn();
    const releases: ((ok: boolean) => void)[] = [];
    const onInsert = vi.fn(() => new Promise<boolean>((resolve) => releases.push(resolve)));
    mount({ onClose, onInsert });
    await click(buttonWithText("Weekly report"));
    mount({ open: false, onClose, onInsert });
    mount({ open: true, onClose, onInsert });
    if (again) await click(buttonWithText("Bug triage"));
    await act(async () => releases[0](true));
    expect(onClose).not.toHaveBeenCalled();
    expect(buttonWithText("Weekly report")?.disabled).toBe(again);
    if (again) {
      await act(async () => releases[1](true));
      expect(onClose).toHaveBeenCalledOnce();
      expect(buttonWithText("Weekly report")?.disabled).toBe(false);
    }
  });
});
