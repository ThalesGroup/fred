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

// Regression: the prompt-field library auto-opens ONLY on the initial empty
// state. Clearing the field while editing (e.g. wiping the system prompt) must
// NOT reopen the library — the user is writing from scratch and can reopen it
// from the "pick from library" button.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TuningFieldRenderer } from "./TuningFieldRenderer";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => {
  // Only the wiki mode options are "translated" — every other key falls through
  // to its defaultValue (or itself), which is what the enum fallback relies on.
  const CATALOG: Record<string, string> = {
    "capability.team_wiki.fields.mode.options.read": "Read only",
    "capability.team_wiki.fields.mode.options.read_write": "Read and propose",
  };
  return {
    useTranslation: () => ({
      t: (key: string, opts?: { defaultValue?: string }) => CATALOG[key] ?? opts?.defaultValue ?? key,
      i18n: { language: "en" },
    }),
  };
});

// One context prompt → the library exists (hasLibrary), so auto-open logic applies.
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({
    data: [{ id: "p1", name: "Prompt 1", scope: "team" }],
  }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: () => ({ data: [] }),
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [vi.fn(), { isLoading: false }],
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation: () => [vi.fn()],
}));

// Keep the picker a simple marker so its presence is trivial to assert.
vi.mock("@shared/molecules/PromptPicker/PromptPicker", () => ({
  PromptPicker: () => <div data-testid="prompt-picker" />,
}));

// Stand in for the CodeMirror editor with a textarea: what is under test here
// is which of the two modes the field shows, not how the editor renders.
vi.mock("@shared/molecules/PromptEditor/PromptEditor", () => ({
  PROMPT_EDITOR_ROWS: 15,
  PromptEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea data-testid="prompt-editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const WIKI_MODE_FIELD = {
  key: "mode",
  type: "string",
  title: "capability.team_wiki.fields.mode.title",
  enum: ["read", "read_write"],
  default: "read",
} as unknown as ManagedAgentFieldSpec;

// Enum values are storage, not copy: a field whose title is an i18n key gets its
// option labels from the same namespace.
const LITERAL_ENUM_FIELD = {
  key: "settings.output_language",
  type: "select",
  title: "Output language",
  enum: ["auto", "fr"],
  default: "auto",
} as unknown as ManagedAgentFieldSpec;

const PROMPT_FIELD = {
  key: "system_prompt",
  type: "prompt",
  title: "System prompt",
  required: false,
} as unknown as ManagedAgentFieldSpec;

let container: HTMLDivElement;
let root: Root;

function renderWithValue(value: string, onChange = vi.fn()) {
  act(() => {
    root.render(
      <TuningFieldRenderer field={PROMPT_FIELD} value={value} onChange={onChange} disabled={false} teamId="t1" />,
    );
  });
}

const pickerShown = () => !!container.querySelector('[data-testid="prompt-picker"]');
const textareaShown = () => !!container.querySelector("textarea");

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("TuningFieldRenderer — prompt library auto-open", () => {
  it("auto-opens the library on the initial EMPTY state", () => {
    renderWithValue("");
    expect(pickerShown()).toBe(true);
    expect(textareaShown()).toBe(false);
  });

  it("shows the textarea (not the library) when the field has a value", () => {
    renderWithValue("Existing prompt");
    expect(textareaShown()).toBe(true);
    expect(pickerShown()).toBe(false);
  });

  it("does NOT reopen the library when the field is cleared by editing", () => {
    // Start with content → textarea (write mode).
    renderWithValue("Existing prompt");
    expect(textareaShown()).toBe(true);

    // User wipes the field in the textarea. Use the native value setter so
    // React's controlled-input value tracker registers the change and fires
    // onChange (a plain `.value = ""` is swallowed by the tracker).
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    act(() => {
      nativeSetter?.call(textarea, "");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    // The form re-renders with the now-empty value (as the parent would).
    renderWithValue("");

    // The library must stay closed — the write-mode textarea is still shown.
    expect(pickerShown()).toBe(false);
    expect(textareaShown()).toBe(true);
  });

  it("keeps the library closed across an unmount/remount once emptied (controlled state)", () => {
    // The form owns pickerExplicit so the decision survives a section switch
    // (which unmounts this field). Emptying it reports write mode upward.
    const changes: (boolean | null)[] = [];
    const onPickerExplicitChange = (v: boolean | null) => changes.push(v);

    act(() => {
      root.render(
        <TuningFieldRenderer
          field={PROMPT_FIELD}
          value="Existing prompt"
          onChange={vi.fn()}
          disabled={false}
          teamId="t1"
          pickerExplicit={null}
          onPickerExplicitChange={onPickerExplicitChange}
        />,
      );
    });
    expect(textareaShown()).toBe(true);

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    act(() => {
      nativeSetter?.call(textarea, "");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(changes).toContain(false); // reported write mode to the form

    // Simulate leaving and returning to the Prompts section: unmount, then
    // remount fresh with the persisted pickerExplicit=false and empty value.
    act(() => root.unmount());
    root = createRoot(container);
    act(() => {
      root.render(
        <TuningFieldRenderer
          field={PROMPT_FIELD}
          value=""
          onChange={vi.fn()}
          disabled={false}
          teamId="t1"
          pickerExplicit={false}
          onPickerExplicitChange={onPickerExplicitChange}
        />,
      );
    });

    expect(pickerShown()).toBe(false);
    expect(textareaShown()).toBe(true);
  });
});

describe("TuningFieldRenderer enum labels", () => {
  const renderField = (field: ManagedAgentFieldSpec, value: unknown) => {
    act(() => {
      root.render(<TuningFieldRenderer field={field} value={value} onChange={vi.fn()} disabled={false} />);
    });
    return container.textContent ?? "";
  };

  it("translates an option through the field's own namespace", () => {
    expect(renderField(WIKI_MODE_FIELD, "read_write")).toContain("Read and propose");
  });

  it("falls back to the raw value when the title is a literal, not a key", () => {
    const text = renderField(LITERAL_ENUM_FIELD, "auto");
    expect(text).toContain("auto");
    expect(text).not.toContain("options.auto");
  });
});
