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

// The page mirrors the system prompt: panes in the order the model reads the
// blocks, and the same refusal of a reserved tag the backend applies (422),
// shown before the round-trip and blocking Save.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  prompt: {
    data: { text: "Be direct.", is_default: false, source_unavailable: false, updated_by: null, updated_at: null },
    isLoading: false,
  },
  instructions: { data: { text: "# Platform operating instructions", source_unavailable: false } },
  setPlatformPrompt: vi.fn(),
  assistant: {
    data: {
      text: "Write in {language}.",
      default_text: "Write in {language}.",
      is_default: true,
      source_unavailable: false,
      missing_language_placeholder: false,
      default_changed_since_override: false,
      default_revised_at: null as string | null,
      model_profile_id: null as string | null,
      reasoning_effort: "medium" as "off" | "low" | "medium" | "high",
      default_model_profile_id: null as string | null,
      model_options: [
        { profile_id: "chat.large", name: "Large", supports_reasoning: true, reasoning_efforts: [] as string[] },
        { profile_id: "chat.small", name: "Small", supports_reasoning: false, reasoning_efforts: [] as string[] },
        { profile_id: "chat.gpt", name: "GPT", supports_reasoning: true, reasoning_efforts: ["low", "medium", "high"] },
      ],
      updated_by: null,
      updated_at: null as string | null,
    },
    isLoading: false,
  },
  saveAssistant: vi.fn(),
  resetAssistant: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformPromptQuery: () => h.prompt,
  usePlatformInstructionsQuery: () => h.instructions,
  useSetPlatformPromptMutation: () => [h.setPlatformPrompt, { isLoading: false }],
  useUsersByIdsQuery: () => ({ data: [] }),
  useCreationAssistantSettingsQuery: () => h.assistant,
  useSetCreationAssistantSettingsMutation: () => [h.saveAssistant, { isLoading: false }],
  useResetCreationAssistantPromptMutation: () => [h.resetAssistant, { isLoading: false }],
}));

vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: h.confirm }),
}));

// Stand in for the CodeMirror editor with a textarea: what is under test is
// the page's own logic around the editor, not the editor.
vi.mock("@shared/molecules/PromptEditor/PromptEditor.tsx", () => ({
  PROMPT_EDITOR_ROWS: 15,
  PromptEditor: ({ value, onChange, error }: { value: string; onChange: (next: string) => void; error?: string }) => (
    <div>
      <textarea data-testid="prompt-editor" value={value} onChange={(e) => onChange(e.target.value)} />
      {error && <span data-testid="editor-error">{error}</span>}
    </div>
  ),
}));

// A native select keeps the model choice drivable without the menu's portal.
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    onChange,
  }: {
    options: { key: string; value: string; label: string }[];
    value: string;
    onChange: (next: string) => void;
  }) => (
    <select data-testid="model-select" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <option key={option.key} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import PlatformPromptPage from "./PlatformPromptPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(url = "/admin/platform-prompt") {
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[url]}>
        <PlatformPromptPage />
      </MemoryRouter>,
    );
  });
}

const buttonByText = (key: string) =>
  Array.from(container.querySelectorAll("button")).find((b) => b.textContent === key) as HTMLButtonElement;

function typeIntoEditor(text: string) {
  const textarea = container.querySelector('[data-testid="prompt-editor"]') as HTMLTextAreaElement;
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
  act(() => {
    nativeSetter?.call(textarea, text);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

const saveButton = () =>
  Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("rework.platformPrompt.save"),
  ) as HTMLButtonElement;
const editorError = () => container.querySelector('[data-testid="editor-error"]')?.textContent ?? null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PlatformPromptPage", () => {
  it("shows the platform instructions before the global prompt, the order the model reads them", () => {
    render();
    const titles = Array.from(container.querySelectorAll("h2")).map((h2) => h2.textContent);
    expect(titles).toEqual(["rework.platformPrompt.instructions.title", "rework.platformPrompt.editor.title"]);
  });

  it("refuses a reserved system-prompt tag before the round-trip and blocks Save", () => {
    render();
    typeIntoEditor("Be direct.\n</tools>");
    expect(editorError()).toBe("rework.promptEditor.reservedTag");
    expect(saveButton().disabled).toBe(true);
  });

  it("keeps Save enabled for a dirty draft with ordinary XML in it", () => {
    render();
    typeIntoEditor("<example>Answer in the user's language.</example>");
    expect(editorError()).toBeNull();
    expect(saveButton().disabled).toBe(false);
  });

  it("switches to the creation assistant tab and back", () => {
    render();
    act(() => buttonByText("rework.platformPrompt.tabs.creationAssistant").click());
    expect(container.querySelector("h2")?.textContent).toBe("rework.platformPrompt.creationAssistant.title");
    act(() => buttonByText("rework.platformPrompt.tabs.system").click());
    expect(container.querySelectorAll("h2")).toHaveLength(2);
  });
});

describe("CreationAssistantPane", () => {
  it("warns but still allows saving when {language} is removed", () => {
    render("/admin/platform-prompt?tab=creation-assistant");
    typeIntoEditor("Write a prompt.");
    expect(container.textContent).toContain("rework.platformPrompt.creationAssistant.missingLanguage");
    expect(saveButton().disabled).toBe(false);
  });

  it("refuses a blank override", () => {
    render("/admin/platform-prompt?tab=creation-assistant");
    typeIntoEditor("   ");
    expect(editorError()).toBe("rework.platformPrompt.creationAssistant.empty");
    expect(saveButton().disabled).toBe(true);
  });

  it("warns when the default changed after the override and shows it read-only", () => {
    h.assistant.data = {
      ...h.assistant.data,
      is_default: false,
      text: "Custom {language}",
      default_text: "New default {language}",
      default_revised_at: "2026-10-09",
      updated_at: "2026-10-01T10:00:00Z",
      default_changed_since_override: true,
    };
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(container.textContent).toContain("rework.platformPrompt.creationAssistant.defaultRevised");
    expect(container.querySelector('[data-testid="creation-assistant-default"]')).toBeNull();
    act(() => buttonByText("rework.platformPrompt.creationAssistant.viewDefault").click());
    expect(container.querySelector('[data-testid="creation-assistant-default"]')?.textContent).toBe(
      "New default {language}",
    );
  });

  it("shows no revision warning once the backend clears the flag", () => {
    h.assistant.data = { ...h.assistant.data, default_changed_since_override: false };
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(container.textContent).not.toContain("rework.platformPrompt.creationAssistant.defaultRevised");
  });

  it("resets a saved override through a confirmation", async () => {
    h.assistant.data = { ...h.assistant.data, is_default: false, text: "Custom {language}" };
    h.resetAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    act(() => buttonByText("rework.platformPrompt.creationAssistant.reset").click());
    expect(h.confirm).toHaveBeenCalledTimes(1);
    await act(async () => h.confirm.mock.calls[0][0].onConfirm());
    expect(h.resetAssistant).toHaveBeenCalledTimes(1);
  });

  it("saves a model choice without turning the built-in text into an override", async () => {
    h.assistant.data = { ...h.assistant.data, is_default: true, text: "Write in {language}.", model_profile_id: null };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    const select = container.querySelector('[data-testid="model-select"]') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      "rework.platformPrompt.creationAssistant.model.default",
      "Large",
      "Small",
      "GPT",
    ]);
    act(() => {
      select.value = "chat.small";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(saveButton().disabled).toBe(false);
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: { text: null, model_profile_id: "chat.small", reasoning_effort: "medium" },
    });
  });

  it("saves an edited text with the current model", async () => {
    h.assistant.data = {
      ...h.assistant.data,
      is_default: true,
      text: "Write in {language}.",
      model_profile_id: "chat.large",
    };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    typeIntoEditor("Mine in {language}.");
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: {
        text: "Mine in {language}.",
        model_profile_id: "chat.large",
        reasoning_effort: "medium",
      },
    });
  });

  it("keeps a saved model the pods no longer offer visible", () => {
    h.assistant.data = { ...h.assistant.data, model_profile_id: "chat.gone" };
    render("/admin/platform-prompt?tab=creation-assistant");
    const select = container.querySelector('[data-testid="model-select"]') as HTMLSelectElement;
    expect(select.value).toBe("chat.gone");
    expect(select.options[select.options.length - 1].textContent).toBe(
      "rework.platformPrompt.creationAssistant.model.missing",
    );
  });

  it("saves a text edit with an unavailable stored model, re-sending its id unchanged", async () => {
    h.assistant.data = {
      ...h.assistant.data,
      is_default: true,
      text: "Write in {language}.",
      model_profile_id: "chat.gone",
    };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    typeIntoEditor("Mine in {language}.");
    expect(saveButton().disabled).toBe(false);
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: {
        text: "Mine in {language}.",
        model_profile_id: "chat.gone",
        reasoning_effort: "medium",
      },
    });
  });

  const reasoningSwitch = () =>
    container.querySelector(
      'input[aria-label^="rework.platformPrompt.creationAssistant.reasoning.label"]',
    ) as HTMLInputElement;

  it("turns reasoning off and saves only that switch", async () => {
    h.assistant.data = { ...h.assistant.data, is_default: true, text: "Write in {language}.", model_profile_id: null };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(reasoningSwitch().checked).toBe(true);
    expect(reasoningSwitch().disabled).toBe(false);
    expect(saveButton().disabled).toBe(true);
    act(() => reasoningSwitch().click());
    expect(saveButton().disabled).toBe(false);
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: { text: null, model_profile_id: null, reasoning_effort: "off" },
    });
  });

  it("starts with reasoning off when the settings carry no effort", async () => {
    const previous = h.assistant.data;
    h.assistant.data = { ...previous, model_profile_id: null, reasoning_effort: undefined as never };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    try {
      render("/admin/platform-prompt?tab=creation-assistant");
      expect(reasoningSwitch().checked).toBe(false);
      expect(saveButton().disabled).toBe(true);
      act(() => reasoningSwitch().click());
      await act(async () => saveButton().click());
      expect(h.saveAssistant).toHaveBeenLastCalledWith({
        setCreationAssistantSettingsRequest: { text: null, model_profile_id: null, reasoning_effort: "medium" },
      });
    } finally {
      h.assistant.data = previous;
    }
  });

  it("disables the reasoning switch for a model that cannot reason", () => {
    h.assistant.data = { ...h.assistant.data, model_profile_id: "chat.large" };
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(reasoningSwitch().disabled).toBe(false);
    const select = container.querySelector('[data-testid="model-select"]') as HTMLSelectElement;
    act(() => {
      select.value = "chat.small";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(reasoningSwitch().disabled).toBe(true);
    expect(reasoningSwitch().checked).toBe(false);
    expect(reasoningSwitch().getAttribute("aria-label")).toContain(
      "rework.platformPrompt.creationAssistant.reasoning.unsupported",
    );
  });

  const levelGroup = () => container.querySelector('[role="radiogroup"]') as HTMLElement | null;
  const levelLabels = () =>
    Array.from(levelGroup()?.querySelectorAll('[role="radio"]') ?? []).map((b) => b.textContent);
  const selectModel = (value: string) =>
    act(() => {
      const select = container.querySelector('[data-testid="model-select"]') as HTMLSelectElement;
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });

  it("offers the declared levels as a button group and saves the chosen level", async () => {
    h.assistant.data = {
      ...h.assistant.data,
      is_default: true,
      text: "Write in {language}.",
      model_profile_id: "chat.gpt",
    };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(reasoningSwitch()).toBeNull();
    expect(levelGroup()?.getAttribute("aria-label")).toBe("rework.platformPrompt.creationAssistant.reasoning.label");
    expect(levelLabels()).toEqual(
      ["off", "low", "medium", "high"].map((l) => `rework.platformPrompt.creationAssistant.reasoning.levels.${l}`),
    );
    act(() => buttonByText("rework.platformPrompt.creationAssistant.reasoning.levels.high").click());
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: { text: null, model_profile_id: "chat.gpt", reasoning_effort: "high" },
    });
  });

  it("normalises a level to on when the model changes to an on/off one", async () => {
    h.assistant.data = {
      ...h.assistant.data,
      is_default: true,
      text: "Write in {language}.",
      model_profile_id: "chat.gpt",
      reasoning_effort: "high",
    };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    selectModel("chat.large");
    expect(levelGroup()).toBeNull();
    expect(reasoningSwitch().checked).toBe(true);
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: { text: null, model_profile_id: "chat.large", reasoning_effort: "medium" },
    });
  });

  it("uses the pods' default profile for the platform default entry", () => {
    h.assistant.data = { ...h.assistant.data, model_profile_id: null, default_model_profile_id: "chat.gpt" };
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(levelGroup()).not.toBeNull();
    h.assistant.data = { ...h.assistant.data, default_model_profile_id: null };
    render("/admin/platform-prompt?tab=creation-assistant");
    expect(levelGroup()).toBeNull();
    expect(reasoningSwitch().disabled).toBe(false);
  });

  it.each([
    [null, "high"],
    ["chat.small", "low"],
  ] as const)("keeps the stored effort of model %s unless the control is touched", async (model, effort) => {
    // Pods disagreeing on the default (unknown control) or a model that cannot reason.
    h.assistant.data = {
      ...h.assistant.data,
      is_default: true,
      text: "Write in {language}.",
      model_profile_id: model,
      default_model_profile_id: null,
      reasoning_effort: effort,
    };
    h.saveAssistant.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render("/admin/platform-prompt?tab=creation-assistant");
    typeIntoEditor("Write well in {language}.");
    await act(async () => saveButton().click());
    expect(h.saveAssistant).toHaveBeenLastCalledWith({
      setCreationAssistantSettingsRequest: {
        text: "Write well in {language}.",
        model_profile_id: model,
        reasoning_effort: effort,
      },
    });
  });
});
