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

// The admin edits a local draft and saves the whole home in one request.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  query: {
    data: undefined as unknown,
    isLoading: false,
    isError: false,
  },
  save: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformHomeQuery: () => h.query,
  useSetPlatformHomeMutation: () => [h.save, { isLoading: false }],
}));

import HomeSettingsSection from "./HomeSettingsSection";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const stored = () => ({
  layout: "advanced",
  featured: [
    { agent_instance_id: "gen", display_name: "Généraliste", team_name: "Groupe", available: true, highlights: [] },
    {
      agent_instance_id: "ppt",
      display_name: "PowerPoint",
      team_name: "Groupe",
      available: false,
      badge: "Nouveau",
      highlights: ["Plan", "Charte"],
    },
  ],
  candidates: [{ agent_instance_id: "word", display_name: "Word", team_id: "g" }],
});

const items = () => Array.from(container.querySelectorAll("li"));
const button = (label: string, scope: ParentNode = container) =>
  Array.from(scope.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === label || b.textContent?.includes(label),
  ) as HTMLButtonElement;
const saveButton = () => button("rework.uiSettings.home.save");

function type(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(element, value);
  act(() => {
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  h.query.data = stored();
  h.save.mockReset();
  h.save.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<HomeSettingsSection />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HomeSettingsSection", () => {
  it("shows the saved order, greys hidden agents and saves nothing until edited", () => {
    expect(items().map((li) => li.textContent?.includes("Généraliste"))).toEqual([true, false]);
    expect(items()[1].getAttribute("data-available")).toBe("false");
    expect(items()[1].textContent).toContain("rework.uiSettings.home.unavailable");
    expect(saveButton().disabled).toBe(true);
  });

  it("reorders, edits extras and switches mode in one request", async () => {
    act(() => button("rework.uiSettings.home.moveDown", items()[0]).click());
    const [first, second] = items();
    type(first.querySelector("input") as HTMLInputElement, "  ");
    type(second.querySelector("input") as HTMLInputElement, " Populaire ");
    type(second.querySelector("textarea") as HTMLTextAreaElement, " Résume \n\n Traduit ");
    act(() => button("rework.uiSettings.home.layouts.classic").click());
    await act(async () => saveButton().click());

    expect(h.save).toHaveBeenCalledWith({
      setPlatformHomeRequest: {
        layout: "classic",
        featured: [
          { agent_instance_id: "ppt", badge: null, highlights: ["Plan", "Charte"] },
          { agent_instance_id: "gen", badge: "Populaire", highlights: ["Résume", "Traduit"] },
        ],
      },
    });
  });

  it("blocks saving with too many highlights and removes an agent", async () => {
    type(items()[0].querySelector("textarea") as HTMLTextAreaElement, "a\nb\nc\nd\ne");
    expect(saveButton().disabled).toBe(true);
    act(() => button("rework.uiSettings.home.remove", items()[0]).click());
    expect(saveButton().disabled).toBe(false);
    await act(async () => saveButton().click());
    expect(h.save).toHaveBeenCalledWith({
      setPlatformHomeRequest: {
        layout: "advanced",
        featured: [{ agent_instance_id: "ppt", badge: "Nouveau", highlights: ["Plan", "Charte"] }],
      },
    });
  });

  it("takes a refetch as is while nothing was edited", () => {
    const next = stored();
    next.featured = [next.featured[1]];
    h.query.data = next;
    act(() => root.render(<HomeSettingsSection />));
    expect(items()).toHaveLength(1);
    expect(items()[0].textContent).toContain("PowerPoint");
  });

  it("keeps the admin's edits on a refetch and refreshes visibility only", () => {
    act(() => button("rework.uiSettings.home.moveDown", items()[0]).click());
    const next = stored();
    next.featured[0].available = false;
    next.featured[1].available = true;
    h.query.data = next;
    act(() => root.render(<HomeSettingsSection />));
    expect(items().map((li) => li.textContent?.includes("PowerPoint"))).toEqual([true, false]);
    expect(items().map((li) => li.getAttribute("data-available"))).toEqual(["true", "false"]);
    expect(saveButton().disabled).toBe(false);
  });
});
