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
import type { ManagedAgentInstanceSummary } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

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

import AgentCard from "./AgentCard";

function instance(): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a1",
    team_id: "team-1",
    template_id: "pod:basic",
    display_name: "Helper",
    role: "Helps",
    status: "enabled",
  };
}

let container: HTMLDivElement;
let root: Root;

function render(agent: ManagedAgentInstanceSummary, canManageAgents: boolean, onPropose?: () => void) {
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
          onPropose={onPropose}
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

describe("AgentCard proposal action", () => {
  it("offers a proposal only when the caller supplies the authorized action", () => {
    const propose = vi.fn();
    render(instance(), true, propose);
    const items = openMenu();
    expect(labels(items)).toContain("rework.localMarketplace.propose");
    act(() => items.find((item) => item.textContent?.includes("localMarketplace.propose"))?.click());
    expect(propose).toHaveBeenCalledOnce();
  });
  it("does not invent actions for a reader", () => {
    render(instance(), false);
    expect(moreButton()).toBeNull();
  });
});

describe("CP preparation state", () => {
  it.each(["pending", "failed"])("blocks chat while %s without changing the voluntary enabled status", (state) => {
    const agent = {
      ...instance(),
      preparation_state: state,
      preparation_error: state === "failed" ? "No usable layouts" : null,
    };
    render(agent, true);
    expect(container.querySelector('[data-enabled="false"]')).not.toBeNull();
    expect(container.textContent).toContain(
      state === "pending" ? "capability.ppt_builder.preparing" : "No usable layouts",
    );
    expect(labels(openMenu())).toContain("rework.agentCard.deactivate");
  });
});
