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
import type { CapabilityEnablementItem } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  binding: undefined as PlatformModelBinding | undefined,
  setBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  deleteBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  setFallback: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  manualModels: [] as CapabilityEnablementItem[],
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
  usePlatformModelFallbackQuery: () => ({ data: { binding: null }, isLoading: false, isError: false }),
  useSetPlatformModelFallbackMutation: () => [h.setFallback, { isLoading: false }],
  useDeletePlatformModelFallbackMutation: () => [vi.fn(), { isLoading: false }],
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
  h.setFallback.mockClear();
  h.binding = undefined;
  h.manualModels = [];
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

function advancedSaveButton(): HTMLButtonElement {
  const button = container.querySelector<HTMLButtonElement>("details button[type=submit]");
  if (!button) throw new Error("advanced save button not rendered");
  return button;
}

describe("PlatformModelBindingsPanel chat-only surface", () => {
  it("renders exactly one row (chat) when unset", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);

    expect(container.textContent).toContain("rework.admin.platformModelBindings.capability.chat");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.language");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.embedding");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.image");
    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(2);
  });

  it("renders the single row even when the backend response is not yet loaded", () => {
    h.binding = undefined;
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);

    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(2);
  });
});

describe("PlatformModelBindingsPanel catalog selector", () => {
  it("preselects the saved model when the API omits null settings", () => {
    h.binding = {
      model_capability: "chat",
      binding: { provider: "openai", name: "gateway-small", settings: { base_url: "https://models.example/v1" } },
    };
    const manual = {
      id: "model__openai__gateway-small",
      name: "gateway-small",
      model_display_name: "Gateway Small",
      model_platform_binding: {
        provider: "openai",
        name: "gateway-small",
        settings: { base_url: "https://models.example/v1", temperature: null },
      },
    } as CapabilityEnablementItem;
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={[manual]} />);
    openEditForm();
    expect(container.querySelector('button[aria-haspopup="listbox"]')?.textContent).toContain("Gateway Small");
  });

  it("selects an advertised discovered model without opening advanced configuration", async () => {
    h.binding = { model_capability: "chat", binding: null };
    const manualModel = {
      id: "model__openai__manual-small",
      name: "manual-small",
      model_display_name: "Manual Small",
      model_platform_binding: { provider: "openai", name: "manual-small" },
    } as CapabilityEnablementItem;
    const discoveredModel = {
      id: "model__openai__gateway-small",
      name: "gateway-small",
      model_display_name: "Gateway Small",
      model_discovery_source_id: "gateway",
      model_platform_binding: {
        provider: "openai",
        name: "gateway-small",
        settings: { base_url: "https://models.example/v1" },
      },
    } as CapabilityEnablementItem;
    render(
      <PlatformModelBindingsPanel
        open
        onClose={() => {}}
        manualModels={[manualModel]}
        discoveredModels={[discoveredModel]}
      />,
    );
    openEditForm();

    expect(container.querySelector("details")?.hasAttribute("open")).toBe(false);
    const selectTrigger = container.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]');
    if (!selectTrigger) throw new Error("model selector not rendered");
    act(() => {
      selectTrigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    const listbox = document.querySelector('[role="listbox"]');
    expect(listbox?.textContent).toContain("rework.admin.platformModelBindings.manualSource");
    expect(listbox?.textContent).toContain("rework.admin.platformModelBindings.discoveredSource");
    expect(listbox?.querySelectorAll('[role="presentation"]')).toHaveLength(2);
    act(() => {
      selectTrigger.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    act(() => {
      selectTrigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    const saveButton = findButton("rework.admin.platformModelBindings.form.save");
    expect(saveButton.hasAttribute("disabled")).toBe(false);
    click(saveButton);
    await act(async () => {});

    expect(h.setBinding).toHaveBeenCalledWith({
      setPlatformModelBindingRequest: { binding: discoveredModel.model_platform_binding },
    });
  });
});

describe("PlatformModelBindingsPanel fallback", () => {
  it("keeps fallback editing separate from the forced binding", async () => {
    h.binding = { model_capability: "chat", binding: null };
    h.manualModels = [
      {
        id: "model-chat-backup",
        name: "chat-backup",
        model_display_name: "Chat backup",
        model_chat_profile_ids: ["manual.chat.backup"],
        model_fallback_profile_ids: ["manual.chat.backup"],
        model_runtime_ids: ["fred"],
      } as CapabilityEnablementItem,
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);
    expect(container.textContent).toContain("rework.admin.platformModelBindings.noFallback");
    const editButtons = buttons().filter(
      (button) => button.textContent === "rework.admin.platformModelBindings.editAction",
    );
    click(editButtons[1]);
    expect(container.textContent).toContain("Chat backup");
    await act(async () => {
      findButton("rework.admin.platformModelBindings.form.save").click();
    });
    expect(h.setFallback).toHaveBeenCalledWith({
      setPlatformModelFallbackRequest: { profile_id: "manual.chat.backup" },
    });
    expect(h.setBinding).not.toHaveBeenCalled();
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);
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
    click(advancedSaveButton());
    await act(async () => {});

    expect(h.setBinding).toHaveBeenCalledWith({
      setPlatformModelBindingRequest: {
        binding: { provider: "openai", name: "gpt-5", settings: nextSettings },
      },
    });
  });

  it("reports invalid JSON inline and disables Save without issuing the mutation", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    typeInto(textarea, "{not valid json");

    expect(container.textContent).toContain("rework.admin.platformModelBindings.form.settingsInvalidJson");
    const saveButton = advancedSaveButton();
    expect(saveButton.hasAttribute("disabled")).toBe(true);

    click(saveButton);
    expect(h.setBinding).not.toHaveBeenCalled();
  });

  it("rejects a non-object JSON value (array) the same way as a syntax error", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    typeInto(textarea, "[1, 2, 3]");

    expect(container.textContent).toContain("rework.admin.platformModelBindings.form.settingsInvalidJson");
    expect(advancedSaveButton().hasAttribute("disabled")).toBe(true);
  });

  it("accepts an empty textarea as an empty settings object", async () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);
    openEditForm();

    const inputs = () => Array.from(container.querySelectorAll("input"));
    typeInto(inputs()[0], "openai");
    typeInto(inputs()[1], "gpt-5");
    typeInto(container.querySelector("textarea") as HTMLTextAreaElement, "");

    const saveButton = advancedSaveButton();
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);

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
    render(<PlatformModelBindingsPanel open onClose={() => {}} manualModels={h.manualModels} />);

    expect(container.textContent).not.toContain("boundState:provider=openai,name=gpt-5");
    expect(container.textContent).toContain("rework.admin.platformModelBindings.podDefault");
  });
});
