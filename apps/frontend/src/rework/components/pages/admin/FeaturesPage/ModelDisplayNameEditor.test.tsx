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
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  setName: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useSetModelDisplayNameMutation: () => [h.setName, { isLoading: false }],
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

import { ModelDisplayNameEditor } from "./ModelDisplayNameEditor";

let container: HTMLDivElement;
let root: Root;

function render(overrideName: string | null = null) {
  if (!container) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  }
  act(() => {
    root.render(
      <ModelDisplayNameEditor
        capabilityId="model__openai__discovered.gateway.abc"
        wireName="chat-a"
        effectiveName={overrideName ?? "Gateway Chat"}
        overrideName={overrideName}
      />,
    );
  });
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent === label || item.getAttribute("aria-label") === label,
  );
  if (!found) throw new Error(`Missing button ${label}`);
  return found;
}

function click(element: Element) {
  act(() => element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
}

function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
  act(() => {
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

afterEach(() => {
  if (root) act(() => root.unmount());
  container?.remove();
  container = undefined as unknown as HTMLDivElement;
  root = undefined as unknown as Root;
  h.setName.mockClear();
});

describe("ModelDisplayNameEditor", () => {
  it("saves an administrator label after discovery and can clear it", async () => {
    render();
    click(button("rework.admin.capabilities.modelName.editAria"));
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.value).toBe("Gateway Chat");
    expect(input.placeholder).toBe("");
    expect(button("rework.admin.capabilities.modelName.saveAction").disabled).toBe(true);
    typeInto(input, "  Team Chat  ");
    click(button("rework.admin.capabilities.modelName.saveAction"));
    await act(async () => {});
    expect(h.setName).toHaveBeenCalledWith({
      capabilityId: "model__openai__discovered.gateway.abc",
      setModelDisplayNameRequest: { display_name: "Team Chat" },
    });

    render("Team Chat");
    click(button("rework.admin.capabilities.modelName.editAria"));
    expect((container.querySelector("input") as HTMLInputElement).value).toBe("Team Chat");
    click(button("rework.admin.capabilities.modelName.resetAction"));
    await act(async () => {});
    expect(h.setName).toHaveBeenLastCalledWith({
      capabilityId: "model__openai__discovered.gateway.abc",
      setModelDisplayNameRequest: { display_name: null },
    });
  });

  it("does not submit a blank name", () => {
    render();
    click(button("rework.admin.capabilities.modelName.editAria"));
    typeInto(container.querySelector("input") as HTMLInputElement, "  ");
    expect(button("rework.admin.capabilities.modelName.saveAction").disabled).toBe(true);
    expect(h.setName).not.toHaveBeenCalled();
  });
});
