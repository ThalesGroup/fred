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

// Regression coverage: the window-level Enter handler used to call onConfirm
// for ANY Enter keydown it saw — including one that started on the Cancel
// button itself (reproduced: confirm=1, cancel=0 when pressing Enter on
// Cancel), on a field that had already committed its own Enter without
// stopping propagation (double-submit — the exact shape of
// SessionTitleEditor's own onKeyDown), or mid IME composition. Fixed to
// leave native button/link/select activation alone and to respect
// `defaultPrevented` and `isComposing`.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dialog } from "./Dialog.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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
  // Dialog's Portal creates this lazily and only tears it down if IT created
  // it; across tests that both open a Dialog, the second reuses the first's
  // leftover node unless cleaned up here.
  document.getElementById("modal-portal")?.remove();
});

function portal(): HTMLElement {
  return document.getElementById("modal-portal") as HTMLElement;
}

function buttonNamed(label: string): HTMLButtonElement {
  const match = Array.from(portal().querySelectorAll("button")).find((b) => b.textContent === label);
  if (!match) throw new Error(`no button named "${label}"`);
  return match;
}

// happy-dom (unlike a real browser) does not synthesize a click from an
// Enter keydown on a focused button/link — the same gap
// @testing-library/user-event works around for jsdom. Reproducing that step
// explicitly is what lets a test on the real Dialog+Button pair observe the
// end-to-end contract: the window handler must not itself act AND must not
// block the native activation a real browser performs.
function pressEnter(target: HTMLElement, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, ...init });
  act(() => {
    target.dispatchEvent(event);
    if (!event.defaultPrevented && (target.tagName === "BUTTON" || target.tagName === "A")) {
      target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    }
  });
  return event;
}

describe("Dialog Enter-key handling", () => {
  it("Enter on the Cancel button invokes only onCancel", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" cancelLabel="Cancel" onConfirm={onConfirm} onCancel={onCancel}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );

    pressEnter(buttonNamed("Cancel"));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter on the Confirm button invokes onConfirm exactly once", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" cancelLabel="Cancel" onConfirm={onConfirm} onCancel={onCancel}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );

    pressEnter(buttonNamed("Save"));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("Enter in the dialog's single-line text input confirms exactly once", () => {
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    const event = pressEnter(input);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("Enter in a textarea does not confirm", () => {
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Note" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <textarea aria-label="note" />
      </Dialog>,
    );
    const textarea = portal().querySelector("textarea") as HTMLTextAreaElement;

    pressEnter(textarea);

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter in a contentEditable surface does not confirm", () => {
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Note" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <div contentEditable data-testid="rich-text" />
      </Dialog>,
    );
    const editable = portal().querySelector("[contenteditable]") as HTMLElement;

    pressEnter(editable);

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter while choosing a Select option does not confirm the Dialog", () => {
    const onConfirm = vi.fn();
    const onChange = vi.fn();
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A" },
      { key: "b", value: "b", label: "B" },
    ];
    render(
      <Dialog open title="Move" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <Select options={options} onChange={onChange} size="medium" />
      </Dialog>,
    );
    const trigger = portal().querySelector('button[aria-haspopup="listbox"]') as HTMLButtonElement;

    act(() => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    });
    act(() => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });

    expect(onChange).toHaveBeenCalledWith("a");
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter does not confirm while the confirm action is disabled", () => {
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" confirmDisabled onConfirm={onConfirm} onCancel={() => {}}>
        <input aria-label="title" />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    pressEnter(input);

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Enter does not confirm while composing an IME candidate", () => {
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    pressEnter(input, { isComposing: true });

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("does not confirm a second time when a descendant already committed its own Enter", () => {
    // Mirrors SessionTitleEditor's real onKeyDown: preventDefault + its own
    // commit, with no stopPropagation. Before the fix, the same keydown
    // reached the window handler afterwards and fired onConfirm too.
    const onConfirm = vi.fn();
    const ownCommit = vi.fn();
    function FieldThatCommitsItsOwnEnter() {
      return (
        <input
          aria-label="title"
          defaultValue="x"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              ownCommit();
            }
          }}
        />
      );
    }
    render(
      <Dialog open title="Rename" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <FieldThatCommitsItsOwnEnter />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    pressEnter(input);

    expect(ownCommit).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("still confirms once from a plain input when no descendant intercepts the Enter", () => {
    // Guards against a fix broad enough to also swallow the legitimate case.
    const onConfirm = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" onConfirm={onConfirm} onCancel={() => {}}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    pressEnter(input);

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("Escape still cancels regardless of focus, unaffected by the fix", () => {
    const onCancel = vi.fn();
    render(
      <Dialog open title="Rename" confirmLabel="Save" onConfirm={() => {}} onCancel={onCancel}>
        <input aria-label="title" defaultValue="x" />
      </Dialog>,
    );
    const input = portal().querySelector("input") as HTMLInputElement;

    act(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
