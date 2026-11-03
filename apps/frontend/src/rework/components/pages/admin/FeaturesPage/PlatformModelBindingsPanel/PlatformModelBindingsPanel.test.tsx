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
import type {
  PlatformModelBinding,
  PodChatDefaultStatus,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  binding: undefined as PlatformModelBinding | undefined,
  setBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  deleteBinding: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  pods: [] as PodChatDefaultStatus[],
  setPodDefault: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  clearPodDefault: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  setPodFallback: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  clearPodFallback: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  assistantSettings: undefined as Record<string, unknown> | undefined,
  assistantSettingsError: false,
  saveAssistantSettings: vi.fn((_request: unknown) => ({ unwrap: () => Promise.resolve() })),
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
  usePodChatDefaultsQuery: () => ({ data: { pods: h.pods }, isLoading: false, isError: false }),
  useSetPodChatDefaultMutation: () => [h.setPodDefault, { isLoading: false }],
  useClearPodChatDefaultMutation: () => [h.clearPodDefault, { isLoading: false }],
  useSetPodChatFallbackMutation: () => [h.setPodFallback, { isLoading: false }],
  useClearPodChatFallbackMutation: () => [h.clearPodFallback, { isLoading: false }],
  useCreationAssistantSettingsQuery: () => ({ data: h.assistantSettings, isError: h.assistantSettingsError }),
  useSetCreationAssistantSettingsMutation: () => [h.saveAssistantSettings, { isLoading: false }],
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
  h.pods = [];
  h.assistantSettings = undefined;
  h.assistantSettingsError = false;
  h.saveAssistantSettings.mockClear();
  h.setPodDefault.mockClear();
  h.clearPodDefault.mockClear();
  h.setPodFallback.mockClear();
  h.clearPodFallback.mockClear();
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
  const button = container.querySelector<HTMLButtonElement>("form button[type=submit]");
  if (!button) throw new Error("save button not rendered");
  return button;
}

describe("PlatformModelBindingsPanel chat-only surface", () => {
  it("renders exactly one row (chat) when unset", () => {
    h.binding = { model_capability: "chat", binding: null };
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);

    expect(container.textContent).toContain("rework.admin.platformModelBindings.capability.chat");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.language");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.embedding");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.capability.image");
    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(1);
  });

  it("renders the single row even when the backend response is not yet loaded", () => {
    h.binding = undefined;
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);

    expect(buttons().filter((b) => b.textContent === "rework.admin.platformModelBindings.editAction")).toHaveLength(1);
  });
});

describe("PlatformModelBindingsPanel agent pod defaults", () => {
  it("shows an inactive YAML default but offers only enabled models for default and fallback", () => {
    h.pods = [
      {
        runtime_id: "fred-agents",
        base_url: "http://fred-agents:8000",
        reachable: true,
        yaml_profile_id: "chat.manual.inactive",
        override_profile_id: null,
        effective_profile_id: "chat.manual.inactive",
        effective_fallback_profile_id: "chat.manual.inactive",
        models: [
          { profile_id: "chat.manual.active", model_id: "manual-active", name: "active", display_name: "Active" },
          {
            profile_id: "discovered.chat.mistral.active",
            model_id: "discovered-active",
            name: "discovered",
            display_name: "Discovered",
            discovery_source_id: "mistral",
          },
        ],
      },
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);

    expect(container.textContent).toContain("chat.manual.inactive");
    const selects = container.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="listbox"]');
    expect(selects[0].textContent).toContain("rework.admin.platformModelBindings.chooseEnabledModel");
    expect(selects[1].textContent).toContain("rework.admin.platformModelBindings.chooseEnabledManualModel");
    click(selects[0]);
    expect(Array.from(document.body.querySelectorAll('[role="option"]')).map((option) => option.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("Active"), expect.stringContaining("Discovered")]),
    );
    expect(
      Array.from(document.body.querySelectorAll('[role="option"]'))
        .map((option) => option.textContent)
        .join(" "),
    ).not.toContain("chat.manual.inactive");
    click(selects[0]);
    click(selects[1]);
    const fallbackOptions = Array.from(document.body.querySelectorAll('[role="option"]'));
    expect(fallbackOptions).toHaveLength(1);
    expect(fallbackOptions[0].textContent).toContain("Active");
  });

  it("offers only manual models as a fallback for the selected pod", async () => {
    h.pods = [
      {
        runtime_id: "fred-agents",
        base_url: "http://fred-agents:8000",
        reachable: true,
        yaml_profile_id: "chat.manual.small",
        override_profile_id: null,
        effective_profile_id: "chat.manual.small",
        effective_fallback_profile_id: "chat.manual.small",
        models: [
          { profile_id: "chat.manual.small", model_id: "manual-small", name: "manual-small", display_name: "Small" },
          { profile_id: "chat.manual.safe", model_id: "manual-safe", name: "manual-safe", display_name: "Safe" },
          {
            profile_id: "discovered.chat.mistral.medium",
            model_id: "discovered-medium",
            name: "discovered-medium",
            display_name: "Medium",
            discovery_source_id: "mistral",
          },
        ],
      },
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);
    const fallbackSelect = container.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="listbox"]')[1];
    click(fallbackSelect);
    const options = Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]'));
    expect(options.map((option) => option.textContent).join(" ")).toContain("Safe");
    expect(options.map((option) => option.textContent).join(" ")).not.toContain("Medium");
    click(options.find((option) => option.textContent?.includes("Safe"))!);
    const saveButtons = buttons().filter(
      (button) => button.textContent === "rework.admin.platformModelBindings.form.save",
    );
    await act(async () => saveButtons[1].click());
    expect(h.setPodFallback).toHaveBeenCalledWith({
      runtimeId: "fred-agents",
      setPodChatFallbackRequest: { profile_id: "chat.manual.safe" },
    });
  });

  it("shortens long discovered profile IDs in the pod selector while retaining the full ID on hover", () => {
    const profileId = `discovered.chat.mistral.${"a".repeat(64)}`;
    h.pods = [
      {
        runtime_id: "fred-agents",
        base_url: "http://fred-agents:8000",
        reachable: true,
        yaml_profile_id: profileId,
        override_profile_id: null,
        effective_profile_id: profileId,
        override_unavailable: false,
        models: [
          {
            profile_id: profileId,
            model_id: "mistral-small",
            name: "mistral-small",
            display_name: "Mistral Small",
            discovery_source_id: "mistral",
          },
        ],
      },
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);

    click(container.querySelector('button[aria-haspopup="listbox"]')!);
    const option = document.body.querySelector('[role="option"]');
    expect(option?.textContent).toContain(`${profileId.slice(0, 33)}...`);
    expect(option?.querySelector("[hidden]")?.textContent).toBe(profileId);
  });

  it("opens the agent pods tab when a required-default dialog changes the initial tab", () => {
    render(<PlatformModelBindingsPanel open={false} onClose={() => {}} initialTab="platform" />);

    act(() => {
      root.render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);
    });

    expect(container.textContent).toContain("rework.admin.platformModelBindings.noPods");
    expect(container.textContent).not.toContain("rework.admin.platformModelBindings.forcedLabel");
    const tabs = container.querySelectorAll('[role="radiogroup"] button');
    expect(tabs[0]?.textContent).toContain("rework.admin.platformModelBindings.podsTab");
    expect(tabs[1]?.textContent).toContain("rework.admin.platformModelBindings.platformTab");
  });

  it("displays the YAML default before an admin override and the saved override afterward", () => {
    h.pods = [
      {
        runtime_id: "fred-agents",
        base_url: "http://fred-agents:8000",
        reachable: true,
        yaml_profile_id: "chat.manual.small",
        override_profile_id: null,
        effective_profile_id: "chat.manual.small",
        override_unavailable: false,
        models: [
          { profile_id: "chat.manual.small", model_id: "manual", name: "manual", display_name: "Small 4" },
          {
            profile_id: "discovered.chat.mistral.medium",
            model_id: "discovered",
            name: "discovered",
            display_name: "Medium 3.5",
            discovery_source_id: "mistral",
          },
        ],
      },
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);

    expect(container.textContent).toContain("fred-agents");
    expect(container.querySelector('button[aria-haspopup="listbox"]')?.textContent).toContain("Small 4");
    expect(findButton("rework.admin.platformModelBindings.form.save").disabled).toBe(true);

    act(() => {
      root.unmount();
    });
    container.remove();
    h.pods = [
      {
        ...h.pods[0],
        override_profile_id: "discovered.chat.mistral.medium",
        effective_profile_id: "discovered.chat.mistral.medium",
      },
    ];
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="pods" />);

    expect(container.querySelector('button[aria-haspopup="listbox"]')?.textContent).toContain("Medium 3.5");
    expect(findButton("rework.admin.platformModelBindings.podResetAction")).toBeTruthy();
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);

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
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);

    expect(container.textContent).not.toContain("boundState:provider=openai,name=gpt-5");
    expect(container.textContent).toContain("rework.admin.platformModelBindings.podDefault");
  });
});

describe("TitleModelSelect", () => {
  it("saves the title model and re-sends the other assistant settings unchanged", async () => {
    h.assistantSettings = {
      is_default: false,
      text: "Mine",
      model_profile_id: "chat.large",
      title_model_profile_id: null,
      reasoning_effort: "high",
      model_options: [{ profile_id: "chat.small", name: "Small" }],
    };
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
    click(container.querySelector('button[aria-haspopup="listbox"]')!);
    const option = Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]')).find((item) =>
      item.textContent?.includes("Small"),
    );
    await act(async () => option!.click());
    expect(h.saveAssistantSettings).toHaveBeenCalledWith({
      setCreationAssistantSettingsRequest: {
        text: "Mine",
        model_profile_id: "chat.large",
        title_model_profile_id: "chat.small",
        reasoning_effort: "high",
      },
    });
  });

  it("explains the missing right instead of showing a selector", () => {
    h.assistantSettingsError = true;
    render(<PlatformModelBindingsPanel open onClose={() => {}} initialTab="platform" />);
    expect(container.textContent).toContain("rework.admin.platformModelBindings.titleModel.loadError");
    expect(container.querySelector('button[aria-haspopup="listbox"]')).toBeNull();
  });
});
