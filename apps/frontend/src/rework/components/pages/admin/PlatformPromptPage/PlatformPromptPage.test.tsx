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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  prompt: {
    data: { text: "Be direct.", is_default: false, source_unavailable: false, updated_by: null, updated_at: null },
    isLoading: false,
  },
  instructions: { data: { text: "# Platform operating instructions", source_unavailable: false } },
  setPlatformPrompt: vi.fn(),
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

import PlatformPromptPage from "./PlatformPromptPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render() {
  act(() => {
    root.render(<PlatformPromptPage />);
  });
}

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
});
