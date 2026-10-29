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

// A field saves on blur, so the two ways out that must not save (Escape, and
// "take theirs" while typing) are checked through real mounts.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WordTemplatePlaceField } from "./WordTemplatePlaceField";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(text: string, apply: () => Promise<boolean>) {
  act(() =>
    root.render(
      <WordTemplatePlaceField
        place={{ address: "P1", text, edit: "set_text", markdown: text }}
        apply={apply}
        variant="field"
      />,
    ),
  );
}

function type(field: HTMLTextAreaElement, value: string) {
  const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setValue.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("WordTemplatePlaceField", () => {
  it("does not save the text when Escape cancels it", async () => {
    const apply = vi.fn(async () => true);
    render("old", apply);
    const field = container.querySelector("textarea")!;
    act(() => field.focus());
    type(field, "new text");
    await act(async () => {
      field.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(apply).not.toHaveBeenCalled();
    expect(field.value).toBe("old");
  });

  it("keeps the AI's change when the collaborator takes theirs while typing", async () => {
    const apply = vi.fn(async () => true);
    render("old", apply);
    const field = container.querySelector("textarea")!;
    act(() => field.focus());
    type(field, "mine");
    render("ai version", apply);
    const button = container.querySelector("button")!;
    expect(button.textContent).toBe("capability.word_template.editor.takeTheirs");
    await act(async () => {
      // A browser moves the focus on mousedown unless it is prevented.
      const press = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
      button.dispatchEvent(press);
      if (!press.defaultPrevented) field.blur();
      button.click();
    });
    expect(apply).not.toHaveBeenCalled();
    expect(field.value).toBe("ai version");
  });
});
