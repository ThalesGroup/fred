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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@mdxeditor/editor", () => ({
  MDXEditor: () => null,
  markdownShortcutPlugin: () => null,
  toolbarPlugin: () => null,
}));
vi.mock("@mdxeditor/editor/style.css", () => ({}));
vi.mock("@shared/organisms/ProseMdxEditor/ProseMdxEditor", () => ({
  ProseToolbarButtons: () => null,
  proseMdxPlugins: () => [],
}));

import { ApplicationContext } from "../../../../app/ApplicationContextProvider";
import { WikiEditor } from "./WikiEditor";

describe("WikiEditor", () => {
  let container: HTMLDivElement;
  let root: Root;
  const onSave = vi.fn();
  const onDelete = vi.fn();

  beforeEach(() => {
    onSave.mockReset();
    onDelete.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const render = (withPlacement: boolean) =>
    act(() => {
      root.render(
        <ApplicationContext.Provider value={{ darkMode: false } as never}>
          <WikiEditor
            title="Onboarding"
            placement={
              withPlacement
                ? {
                    parentId: "",
                    parentOptions: [
                      { value: "", key: "__root__", label: "root" },
                      { value: "p-2", key: "p-2", label: "Tooling" },
                    ],
                    onDelete,
                  }
                : undefined
            }
            initialContent="hello"
            maxChars={1000}
            saving={false}
            conflict={null}
            onSave={onSave}
            onCancel={vi.fn()}
            onTakeTheirs={vi.fn()}
          />
        </ApplicationContext.Provider>,
      );
    });

  const button = (label: string) =>
    [...container.querySelectorAll("button")].find(
      (b) => b.textContent === label || b.getAttribute("aria-label") === label,
    );

  it("edits the title of an ordinary page and saves it with the text", () => {
    render(true);
    const input = container.querySelector("input")!;
    expect(input.value).toBe("Onboarding");
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "  Getting started ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.querySelector("h1")?.textContent).toBe("Getting started");
    act(() => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith("hello", { title: "Getting started", parentId: "" });
  });

  it("asks to delete from the error-colored icon button", () => {
    render(true);
    act(() => button("rework.wiki.editor.delete")!.click());
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("keeps the rules page title fixed, with no parent and no delete", () => {
    render(false);
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("h1")?.textContent).toBe("Onboarding");
    expect(button("rework.wiki.editor.delete")).toBeUndefined();
    act(() => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith("hello", null);
  });
});
