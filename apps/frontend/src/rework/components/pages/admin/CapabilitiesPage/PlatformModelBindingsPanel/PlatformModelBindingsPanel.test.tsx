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

// This surface is chat-only: the panel renders exactly one row (chat), never
// a 4-capability list. Locks in: the JSON settings editor preserves
// booleans/numbers/strings on save (no String()/Object.fromEntries
// coercion); invalid JSON is reported inline and blocks Save without issuing
// the mutation; and Reset ("delete") fires the mutation and the row reflects
// "using pod default" again once the query result catches up (simulating the
// post-invalidation refetch).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlatformModelBinding } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  binding: undefined as PlatformModelBinding | undefined,
  setBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  deleteBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (!opts) return key;
      const { defaultValue, ...rest } = opts;
      const restEntries = Object.entries(rest);
      if (defaultValue !== undefined && restEntries.length === 0) return String(defaultValue);
      if (restEntries.length === 0) return key;
      return `${key}:${restEntries.map(([k, v]) => `${k}=${v}`).join(",")}`;
    },
  }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformModelBindingQuery: () => ({ data: h.binding, isLoading: false, isError: false }),
  useSetPlatformModelBindingMutation: () => [h.setBinding, { isLoading: false }],
  useDeletePlatformModelBindingMutation: () => [h.deleteBinding, { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

import { PlatformModelBindingsPanel } from "./PlatformModelBindingsPanel";

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.setBinding.mockClear();
  h.deleteBinding.mockClear();
  h.binding = undefined;
});

function buttons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button"));
}

function findButton(text: string): HTMLButtonElement {
  const btn = buttons().find((b) => b.textContent === text);
  if (!btn) throw new Error(`button ${JSON.stringify(text)} not rendered`);
  return btn;
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto =
    input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  act(() => {
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function openEditForm() {
  click(findButton("rework.admin.platformModelBindings.editAction"));
}

describe("PlatformModelBindingsPanel chat-only surface", () => {
  it("renders exactly one row (chat) when unset", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);

    expect(container.textContent).toContain("rework.admin.platformModelBindings.capability.chat");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.language");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.embedding");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.image");
    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(1);
  });

  it("renders the single row even when the backend response is not yet loaded", () => {
    h.binding = undefined;
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);

    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(1);
  });
});

describe("PlatformModelBindingsPanel JSON settings editor", () => {
  it("seeds the textarea from JSON.stringify of the current settings and preserves types on save (bool/int/float/string)", async () => {
    h.binding = {
      model_capability: "chat",
      binding: {
        provider: "openai",
        name: "gpt-5",
        settings: {
          temperature: 0.2,
          streaming: true,
          max_tokens: 4096,
          azure_openai_api_version: "2024-05-01",
        },
      },
    };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);
    openEditForm();

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(JSON.parse(textarea.value)).toEqual({
      temperature: 0.2,
      streaming: true,
      max_tokens: 4096,
      azure_openai_api_version: "2024-05-01",
    });

    const nextSettings = {
      temperature: 0.5,
      streaming: false,
      max_tokens: 128,
      top_p: 0.9,
      azure_openai_api_version: "2024-08-01",
    };
    typeInto(textarea, JSON.stringify(nextSettings));
    click(findButton("rework.admin.platformModelBindings.form.save"));
    await act(async () => {});

    expect(h.setBinding).toHaveBeenCalledWith({
      setPlatformModelBindingRequest: {
        binding: { provider: "openai", name: "gpt-5", settings: nextSettings },
      },
    });
  });

  it("reports invalid JSON inline and disables Save without issuing the mutation", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    typeInto(textarea, "{not valid json");

    expect(container.textContent).toContain("rework.admin.platformModelBindings.form.settingsInvalidJson");
    const saveButton = findButton("rework.admin.platformModelBindings.form.save");
    expect(saveButton.hasAttribute("disabled")).toBe(true);

    click(saveButton);
    expect(h.setBinding).not.toHaveBeenCalled();
  });

  it("rejects a non-object JSON value (array) the same way as a syntax error", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    typeInto(textarea, "[1, 2, 3]");

    expect(container.textContent).toContain("rework.admin.platformModelBindings.form.settingsInvalidJson");
    expect(findButton("rework.admin.platformModelBindings.form.save").hasAttribute("disabled")).toBe(true);
  });

  it("accepts an empty textarea as an empty settings object", async () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");
    typeInto(container.querySelector("textarea") as HTMLTextAreaElement, "");

    const saveButton = findButton("rework.admin.platformModelBindings.form.save");
    expect(saveButton.hasAttribute("disabled")).toBe(false);
    click(saveButton);
    await act(async () => {});

    expect(h.setBinding).toHaveBeenCalledWith({
      setPlatformModelBindingRequest: {
        binding: { provider: "openai", name: "gpt-5", settings: {} },
      },
    });
  });
});

describe("PlatformModelBindingsPanel delete/reset", () => {
  it("fires the delete mutation, then reflects the pod-default state once the query catches up", () => {
    h.binding = { model_capability: "chat", binding: { provider: "openai", name: "gpt-5", settings: {} } };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);

    expect(container.textContent).toContain("boundState:provider=openai,name=gpt-5");

    const deleteButton = buttons().find(
      (b) => b.getAttribute("aria-label") === "rework.admin.platformModelBindings.deleteAction",
    );
    if (!deleteButton) throw new Error("delete button not rendered for a bound row");
    click(deleteButton);

    expect(h.deleteBinding).toHaveBeenCalledWith();

    // Simulate the post-invalidation refetch. Remount against the fresh
    // query result (the prior root is torn down explicitly so it doesn't
    // leak into the next render below).
    act(() => {
      root.unmount();
    });
    container.remove();
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} />);

    expect(container.textContent).not.toContain("boundState:provider=openai,name=gpt-5");
    expect(container.textContent).toContain("rework.admin.platformModelBindings.podDefault");
  });
});
