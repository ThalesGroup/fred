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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/atoms/Icon/Icon.tsx", () => ({ default: () => null }));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "person" }),
}));

import FeaturedCarousel, { AUTOPLAY_MS } from "./FeaturedCarousel";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const agent = (id: string) => ({
  agent_instance_id: id,
  team_id: "team",
  template_id: "tpl",
  display_name: `Agent ${id}`,
  role: `Pitch ${id}`,
  description: `Description ${id}`,
  status: "enabled" as const,
});

let container: HTMLDivElement;
let root: Root;

function render(ids: string[], extras: { badge?: string; highlights?: string[] } = {}) {
  const featured = ids.map((id, i) => ({ agent: agent(id), ...(i === 0 ? extras : {}) }));
  act(() =>
    root.render(
      <MemoryRouter>
        <FeaturedCarousel featured={featured} teamName={() => "Groupe"} />
      </MemoryRouter>,
    ),
  );
}

const shown = () => container.querySelector("h3")?.textContent;
const button = (label: string) => container.querySelector(`button[aria-label="${label}"]`) as HTMLButtonElement | null;
const banner = () => container.querySelector("article") as HTMLElement;

beforeEach(() => {
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

describe("FeaturedCarousel", () => {
  it("rotates on its own, in admin order, and loops", () => {
    render(["a", "b", "c"]);
    expect(shown()).toBe("Agent a");
    act(() => vi.advanceTimersByTime(AUTOPLAY_MS));
    expect(shown()).toBe("Agent b");
    act(() => vi.advanceTimersByTime(2 * AUTOPLAY_MS));
    expect(shown()).toBe("Agent a");
    expect(container.querySelector('a[href="/team/team/managed-chat/a"]')).not.toBeNull();
  });

  it("stops rotating once the user navigates or pauses", () => {
    render(["a", "b", "c"]);
    act(() => button("rework.home.advanced.previous")!.click());
    expect(shown()).toBe("Agent c");
    act(() => vi.advanceTimersByTime(3 * AUTOPLAY_MS));
    expect(shown()).toBe("Agent c");
    expect(button("rework.home.advanced.play")).not.toBeNull();
  });

  it("holds while hovered and resumes after", () => {
    render(["a", "b"]);
    act(() => banner().dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    act(() => vi.advanceTimersByTime(2 * AUTOPLAY_MS));
    expect(shown()).toBe("Agent a");
    act(() => banner().dispatchEvent(new MouseEvent("mouseout", { bubbles: true })));
    act(() => vi.advanceTimersByTime(AUTOPLAY_MS));
    expect(shown()).toBe("Agent b");
  });

  it("hides the controls for one agent and shows extras only when set", () => {
    render(["a"]);
    expect(button("rework.home.advanced.next")).toBeNull();
    expect(container.textContent).not.toContain("rework.home.advanced.highlightsTitle");
    render(["a"], { badge: "Nouveau", highlights: ["Résume"] });
    expect(container.textContent).toContain("Nouveau");
    expect(container.textContent).toContain("Résume");
  });
});
