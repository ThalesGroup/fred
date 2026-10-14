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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AgentMarketplaceState,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy" }),
}));

import AgentCard, { type AgentCardMarketplace } from "./AgentCard";

const PUBLISHED: AgentMarketplaceState = {
  state: "published",
  version: 3,
  published_at: "2026-10-01T10:00:00Z",
  like_count: 4,
  import_count: 7,
};

function instance(marketplace: AgentMarketplaceState | null = null): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a1",
    team_id: "team-1",
    template_id: "pod:basic",
    display_name: "Helper",
    role: "Helps",
    status: "enabled",
    marketplace,
  };
}

function marketplaceProps(over: Partial<AgentCardMarketplace> = {}): AgentCardMarketplace {
  return {
    showBar: true,
    canRemove: false,
    showDetailedState: true,
    canHide: false,
    onPublish: vi.fn(),
    onRemove: vi.fn(),
    onHide: vi.fn(),
    ...over,
  };
}

let container: HTMLDivElement;
let root: Root;

function render(agent: ManagedAgentInstanceSummary, canManageAgents: boolean, marketplace?: AgentCardMarketplace) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <MemoryRouter>
        <AgentCard
          instance={agent}
          teamId="team-1"
          canManageAgents={canManageAgents}
          onEdit={vi.fn()}
          onToggleEnabled={vi.fn()}
          onDuplicate={vi.fn()}
          onCopyTo={vi.fn()}
          onDelete={vi.fn()}
          marketplace={marketplace}
        />
      </MemoryRouter>,
    );
  });
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const moreButton = () => container.querySelector('[aria-label="rework.agentCard.moreMenu"]') as HTMLElement | null;

function openMenu(): HTMLElement[] {
  const button = moreButton();
  if (!button) throw new Error("no more menu");
  act(() => button.click());
  return Array.from(document.querySelectorAll('[role="option"]')) as HTMLElement[];
}

// The icon's ligature text is part of textContent; keep the label only.
const labels = (items: HTMLElement[]) =>
  items.map((item) => {
    const icon = item.querySelector('[aria-hidden="true"]')?.textContent ?? "";
    return item.textContent?.replace(icon, "").trim();
  });

describe("AgentCard more menu", () => {
  it("gives a team admin who is not an editor a menu with Remove only", () => {
    render(instance(PUBLISHED), false, marketplaceProps({ canRemove: true, showDetailedState: true, canHide: true }));
    expect(labels(openMenu())).toEqual(["rework.agentMarketplace.menu.remove"]);
  });

  it("renders no menu for a member who can neither edit nor remove", () => {
    render(instance(PUBLISHED), false, marketplaceProps({ showDetailedState: false }));
    expect(moreButton()).toBeNull();
  });

  it("shows Publish when the page offers it and no marketplace item otherwise", () => {
    render(instance(), true, marketplaceProps({ publishAction: { kind: "publish" } }));
    expect(labels(openMenu())).toContain("rework.agentMarketplace.menu.publish");
    act(() => root.unmount());
    container.remove();
    document.body.innerHTML = "";

    render(instance(PUBLISHED), true, marketplaceProps());
    const items = labels(openMenu());
    expect(items).not.toContain("rework.agentMarketplace.menu.publish");
    expect(items).not.toContain("rework.agentMarketplace.menu.republish");
    expect(items).not.toContain("rework.agentMarketplace.menu.remove");
    expect(items).toContain("rework.agentCard.edit");
  });

  it("greys a blocked publication with its reason as tooltip", () => {
    const onPublish = vi.fn();
    render(
      instance(),
      true,
      marketplaceProps({ publishAction: { kind: "publish", disabledReason: "Quota reached" }, onPublish }),
    );
    const item = openMenu().find((el) => el.textContent?.includes("menu.publish"));
    expect(item?.getAttribute("aria-disabled")).toBe("true");
    // A real Tooltip on the whole row, not a native title.
    expect(item?.getAttribute("title")).toBeNull();
    // Focus stays on the list, so the reason must describe the option itself.
    const describedBy = item?.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy)?.textContent).toBe("Quota reached");
    const trigger = item?.querySelector('[data-fill="true"]');
    act(() => trigger?.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe("Quota reached");
    act(() => item?.click());
    expect(onPublish).not.toHaveBeenCalled();
  });

  it("offers Republish and Remove on a published agent", () => {
    const onPublish = vi.fn();
    render(
      instance(PUBLISHED),
      true,
      marketplaceProps({ publishAction: { kind: "republish" }, canRemove: true, onPublish }),
    );
    const items = openMenu();
    expect(labels(items)).toEqual(
      expect.arrayContaining(["rework.agentMarketplace.menu.republish", "rework.agentMarketplace.menu.remove"]),
    );
    act(() => items.find((el) => el.textContent?.includes("menu.republish"))?.click());
    expect(onPublish).toHaveBeenCalledOnce();
  });
});

describe("AgentCard marketplace bar", () => {
  const bar = () => container.querySelector('[aria-label="rework.agentMarketplace.barLabel"]');

  it("shows no bar for an unpublished agent, with Publish in the more menu", () => {
    render(instance(), true, marketplaceProps({ publishAction: { kind: "publish" } }));
    expect(bar()).toBeNull();
    expect(container.querySelector('[aria-label="rework.agentCard.moreMenu"]')).not.toBeNull();
  });

  it("shows no bar for unpublished or dismissed agents", () => {
    render(instance(), false, marketplaceProps({ showDetailedState: false }));
    expect(bar()).toBeNull();
    act(() => root.unmount());
    container.remove();
    render(instance({ ...PUBLISHED, state: "dismissed" }), true, marketplaceProps());
    expect(bar()).toBeNull();
  });

  it("shows no bar when the team cannot publish", () => {
    render(instance(PUBLISHED), true, marketplaceProps({ showBar: false }));
    expect(bar()).toBeNull();
  });

  it("shows Published with the like and import counters", () => {
    render(instance(PUBLISHED), true, marketplaceProps());
    expect(bar()?.getAttribute("data-tone")).toBe("neutral");
    expect(bar()?.textContent).toContain("rework.agentMarketplace.published");
    expect(container.querySelector('[aria-label^="rework.agentMarketplace.likes"]')?.textContent).toContain("4");
    expect(container.querySelector('[aria-label^="rework.agentMarketplace.imports"]')?.textContent).toContain("7");
  });

  it("shows Modified in the warning tone to editors, counters kept", () => {
    render(instance({ ...PUBLISHED, modified: true }), true, marketplaceProps());
    expect(bar()?.getAttribute("data-tone")).toBe("warning");
    expect(bar()?.textContent).toContain("rework.agentMarketplace.modified.label");
    expect(container.querySelector('[aria-label^="rework.agentMarketplace.likes"]')).not.toBeNull();
  });

  it("shows a member only Published, never Modified or Removed", () => {
    render(instance({ ...PUBLISHED, modified: true }), false, marketplaceProps({ showDetailedState: false }));
    expect(bar()?.getAttribute("data-tone")).toBe("neutral");
    expect(bar()?.textContent).toContain("rework.agentMarketplace.published");
    act(() => root.unmount());
    container.remove();
    render(
      instance({ ...PUBLISHED, state: "removed", removed_reason: "deactivated" }),
      false,
      marketplaceProps({ showDetailedState: false }),
    );
    expect(bar()).toBeNull();
  });

  it("opens the Removed popover with reason, date, admin message and Hide for editors", () => {
    const onHide = vi.fn();
    render(
      instance({
        ...PUBLISHED,
        state: "removed",
        removed_reason: "removed_by_platform_admin",
        removed_at: "2026-10-02T09:00:00Z",
        removed_message: "Outdated instructions",
      }),
      true,
      marketplaceProps({ canHide: true, onHide }),
    );
    const trigger = bar()?.querySelector("button[aria-expanded]") as HTMLButtonElement;
    act(() => trigger.click());
    const popover = container.querySelector('[role="dialog"]');
    expect(popover?.textContent).toContain("reasons.removed_by_platform_admin");
    expect(popover?.textContent).toContain("rework.agentMarketplace.removed.date");
    expect(popover?.textContent).toContain("Outdated instructions");
    const hide = Array.from(popover?.querySelectorAll("button") ?? []).find((b) =>
      b.textContent?.includes("removed.hide"),
    );
    act(() => hide?.click());
    expect(onHide).toHaveBeenCalledOnce();
  });

  it("gives a plain editor no Hide in the Removed popover", () => {
    render(
      instance({ ...PUBLISHED, state: "removed", removed_reason: "suspended", removed_at: "2026-10-02T09:00:00Z" }),
      true,
      marketplaceProps({ canHide: false }),
    );
    act(() => (bar()?.querySelector("button[aria-expanded]") as HTMLButtonElement).click());
    const popover = container.querySelector('[role="dialog"]');
    expect(popover?.textContent).toContain("reasons.suspended");
    expect(popover?.textContent).not.toContain("removed.hide");
  });
});
