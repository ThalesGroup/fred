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

// The agents marketplace page: server order kept, search and the team filter
// set from a card,
// explanatory empty states, and the cards' Like toggle.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceAgentSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  agents: [] as unknown[],
  like: vi.fn(),
  unlike: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn() }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy" }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplaceAgentsQuery: () => ({ data: h.agents, isLoading: false, isUninitialized: false, isError: false }),
  useLikeMarketplaceAgentMutation: () => [h.like],
  useUnlikeMarketplaceAgentMutation: () => [h.unlike],
}));
// The dialogs have their own suites.
vi.mock("./MarketplaceAgentDialog/MarketplaceAgentDialog.tsx", () => ({
  default: ({ agent }: { agent: MarketplaceAgentSummary | null }) =>
    agent ? <div data-testid="id-card">{agent.entry_id}</div> : null,
}));
vi.mock("./ImportAgentDialog/ImportAgentDialog.tsx", () => ({
  default: ({ agent }: { agent: MarketplaceAgentSummary | null }) =>
    agent ? <div data-testid="import">{agent.entry_id}</div> : null,
}));

import MarketplaceAgents from "./MarketplaceAgents";

const agent = (over: Partial<MarketplaceAgentSummary>): MarketplaceAgentSummary => ({
  entry_id: "e",
  team_id: "team-a",
  team_name: "Alpha",
  template_id: "pod:basic",
  display_name: "Agent",
  description: "",
  role: "Helper",
  version: 1,
  first_published_at: "2026-09-01T10:00:00Z",
  published_at: "2026-10-01T10:00:00Z",
  like_count: 0,
  import_count: 0,
  liked_by_me: false,
  ...over,
});

const names = () => Array.from(document.querySelectorAll('[data-enabled="true"]')).map((c) => c.textContent ?? "");

function typeInto(input: HTMLInputElement, value: string) {
  act(() => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("MarketplaceAgents", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<MarketplaceAgents />));
  };

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    h.agents = [];
    h.like.mockReset();
    h.unlike.mockReset();
  });

  it("explains an empty marketplace", () => {
    render();
    expect(document.body.textContent).toContain("rework.marketplace.agents.empty.title");
    expect(document.body.textContent).toContain("rework.marketplace.agents.empty.description");
    expect(document.querySelector("input")).toBeNull();
  });

  const buttonLabelled = (label: string) =>
    Array.from(document.querySelectorAll("button")).find((b) => b.getAttribute("aria-label") === label)!;

  const searchInput = () =>
    Array.from(document.querySelectorAll("input")).find(
      (i) => i.getAttribute("placeholder") === "rework.marketplace.agents.searchPlaceholder",
    )!;

  it("keeps the server order and shows the team, the date and no chat or more menu", () => {
    h.agents = [agent({ entry_id: "new", display_name: "Newest" }), agent({ entry_id: "old", display_name: "Oldest" })];
    render();
    const cards = names();
    expect(cards[0]).toContain("Newest");
    expect(cards[1]).toContain("Oldest");
    expect(cards[0]).toContain("rework.marketplace.agents.card.byTeam Alpha");
    expect(cards[0]).toContain("rework.marketplace.agents.card.updatedOn");
    expect(document.body.textContent).not.toContain("rework.agentCard.chat");
    expect(document.querySelector('[aria-label="rework.agentCard.moreMenu"]')).toBeNull();
    expect(document.querySelector('[role="switch"]')).toBeNull();
  });

  it("shows the no-result state for a search without match", () => {
    h.agents = [agent({ entry_id: "a", display_name: "Analyst" })];
    render();
    typeInto(searchInput(), "zzz");
    expect(document.body.textContent).toContain("rework.marketplace.agents.emptySearch.title");
    typeInto(searchInput(), "analy");
    expect(names()).toHaveLength(1);
  });

  it("has a single search field that also matches team names, accents and case aside", () => {
    h.agents = [
      agent({ entry_id: "a", display_name: "First", team_name: "Équipe Communication" }),
      agent({ entry_id: "b", display_name: "Second", team_id: "team-b", team_name: "Beta" }),
    ];
    render();
    expect(document.querySelectorAll("input")).toHaveLength(1);
    typeInto(searchInput(), "equipe COMM");
    expect(names()).toHaveLength(1);
    expect(names()[0]).toContain("First");
  });

  it("filters on a card's team, shows a removable chip, and keeps it on an empty result", () => {
    h.agents = [
      agent({ entry_id: "a", display_name: "From Alpha" }),
      agent({ entry_id: "b", display_name: "From Beta", team_id: "team-b", team_name: "Beta" }),
    ];
    render();
    const teamLink = buttonLabelled('rework.marketplace.agents.card.filterByTeam {"team":"Beta"}');
    act(() => teamLink.click());
    expect(names()).toHaveLength(1);
    expect(names()[0]).toContain("From Beta");
    expect(document.querySelector('[data-testid="id-card"]')).toBeNull();
    expect(document.body.textContent).toContain('rework.marketplace.agents.teamFilter.chip {"team":"Beta"}');

    typeInto(searchInput(), "zzz");
    expect(document.body.textContent).toContain("rework.marketplace.agents.emptySearch.title");
    typeInto(searchInput(), "");

    const remove = buttonLabelled('rework.marketplace.agents.teamFilter.clear {"team":"Beta"}');
    act(() => remove.click());
    expect(names()).toHaveLength(2);
    expect(document.body.textContent).not.toContain("rework.marketplace.agents.teamFilter.chip");
  });

  it("toggles a like with a pressed state, own team included", async () => {
    h.like.mockReturnValue({ unwrap: async () => ({}) });
    h.unlike.mockReturnValue({ unwrap: async () => ({}) });
    h.agents = [agent({ entry_id: "a", like_count: 2 }), agent({ entry_id: "b", like_count: 3, liked_by_me: true })];
    render();
    const likeButtons = Array.from(document.querySelectorAll("button[aria-pressed]"));
    expect(likeButtons.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "true"]);
    await act(async () => (likeButtons[0] as HTMLButtonElement).click());
    await act(async () => (likeButtons[1] as HTMLButtonElement).click());
    expect(h.like).toHaveBeenCalledWith({ entryId: "a" });
    expect(h.unlike).toHaveBeenCalledWith({ entryId: "b" });
  });

  it("ignores a second click while a like is pending without dropping focus", async () => {
    let resolve: (value: unknown) => void = () => {};
    h.like.mockReturnValue({ unwrap: () => new Promise((r) => (resolve = r)) });
    h.agents = [agent({ entry_id: "a" })];
    render();
    const button = document.querySelector("button[aria-pressed]") as HTMLButtonElement;
    button.focus();
    await act(async () => button.click());
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.disabled).toBe(false);
    expect(document.activeElement).toBe(button);
    await act(async () => button.click());
    expect(h.like).toHaveBeenCalledOnce();
    await act(async () => resolve({}));
    expect(button.getAttribute("aria-disabled")).toBeNull();
  });

  it("opens the ID card and the import dialog from a card", () => {
    h.agents = [agent({ entry_id: "a" })];
    render();
    const details = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("rework.marketplace.agents.card.details"),
    );
    act(() => details?.click());
    expect(document.querySelector('[data-testid="id-card"]')?.textContent).toBe("a");
    const importButton = Array.from(document.querySelectorAll("button")).find((b) =>
      b.getAttribute("aria-label")?.startsWith("rework.marketplace.agents.card.import"),
    );
    act(() => importButton?.click());
    expect(document.querySelector('[data-testid="import"]')?.textContent).toBe("a");
  });
});
