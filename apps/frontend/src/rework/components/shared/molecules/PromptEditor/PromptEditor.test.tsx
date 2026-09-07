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

import { undo } from "@codemirror/commands";
import { EditorView } from "@codemirror/view";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PromptEditor } from "./PromptEditor";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const docText = () => container.querySelector(".cm-content")?.textContent ?? "";

function render(props: Partial<Parameters<typeof PromptEditor>[0]> = {}) {
  act(() => {
    root.render(<PromptEditor label="System prompt" value="" onChange={vi.fn()} {...props} />);
  });
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PromptEditor", () => {
  it("mounts the editor on the value it is given", () => {
    render({ value: "# Title\n\n<instructions>do this</instructions>" });
    expect(docText()).toContain("# Title");
    expect(docText()).toContain("<instructions>");
  });

  it("names the editing surface after the label (it is not a form control)", () => {
    render({ label: "System prompt" });
    const content = container.querySelector(".cm-content");
    const labelId = content?.getAttribute("aria-labelledby");
    expect(labelId).toBeTruthy();
    expect(container.querySelector(`#${CSS.escape(labelId!)}`)?.textContent).toBe("System prompt");
  });

  it("marks a required field on the label", () => {
    render({ label: "System prompt", required: true });
    expect(container.textContent).toContain("System prompt *");
  });

  it("adopts a value changed from outside without echoing it back", () => {
    const onChange = vi.fn();
    render({ value: "first", onChange });
    expect(docText()).toContain("first");
    render({ value: "picked from the library", onChange });
    expect(docText()).toContain("picked from the library");
    expect(docText()).not.toContain("first");
    // Only real edits are reported: an echo here would have the parent write
    // back a value the editor already holds.
    expect(onChange).not.toHaveBeenCalled();
  });

  // The guard that keeps the caret in place: a re-render carrying the value the
  // editor already holds must not dispatch a document replacement.
  it("leaves the document untouched when re-rendered with the same value", () => {
    const onChange = vi.fn();
    render({ value: "stable", onChange });
    render({ value: "stable", onChange });
    expect(docText()).toContain("stable");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("reports what the user types", () => {
    const onChange = vi.fn();
    render({ value: "hello", onChange });
    const view = EditorView.findFromDOM(container.querySelector(".cm-editor") as HTMLElement);
    act(() => {
      view?.dispatch({ changes: { from: 5, insert: " world" } });
    });
    expect(onChange).toHaveBeenCalledWith("hello world");
  });

  // PromptsPage mounts the editor empty and seeds it once the prompt detail
  // resolves. That seeding is not an edit: undoing past it would wipe the
  // prompt and report the erasure as the user's own.
  it("keeps a value seeded after mount out of the undo history", () => {
    const onChange = vi.fn();
    render({ value: "", onChange });
    render({ value: "seeded from the server", onChange });

    const view = EditorView.findFromDOM(container.querySelector(".cm-editor") as HTMLElement);
    act(() => {
      view?.dispatch({ changes: { from: 22, insert: " plus my edit" } });
    });
    expect(onChange).toHaveBeenLastCalledWith("seeded from the server plus my edit");

    act(() => {
      undo({ state: view!.state, dispatch: (tr) => view!.dispatch(tr) });
    });
    expect(docText()).toContain("seeded from the server");

    // One more undo must not reach past the seed into the empty document.
    act(() => {
      undo({ state: view!.state, dispatch: (tr) => view!.dispatch(tr) });
    });
    expect(docText()).toContain("seeded from the server");
  });

  it("shows an error under the field", () => {
    render({ error: "Too long" });
    expect(container.textContent).toContain("Too long");
  });

  it("applies a placeholder set after mount", () => {
    render({ value: "" });
    expect(container.querySelector(".cm-placeholder")).toBeNull();
    render({ value: "", placeholder: "Describe what the agent should do" });
    expect(container.querySelector(".cm-placeholder")?.textContent).toBe("Describe what the agent should do");
  });

  it("stops being editable when disabled", () => {
    render({ value: "text", disabled: true });
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
  });
});
