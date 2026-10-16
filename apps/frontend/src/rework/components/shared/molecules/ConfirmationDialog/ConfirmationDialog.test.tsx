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

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DialogPrimitive } from "../Dialog/DialogPrimitive";
import { FullPageModal } from "../FullPageModal/FullPageModal";
import { ConfirmationDialog } from "./ConfirmationDialog";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.getElementById("modal-portal")?.remove();
});

const confirmation = () => document.querySelector('[role="alertdialog"]') as HTMLElement;
const buttonIn = (scope: ParentNode, label: string) =>
  [...scope.querySelectorAll("button")].find((node) => node.textContent === label) as HTMLButtonElement;

function press(key: string, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  act(() => {
    (document.activeElement ?? document.body).dispatchEvent(event);
  });
  return event;
}

type Handlers = { dialogConfirm?: () => void; dialogCancel?: () => void; formClose?: () => void };

/** A confirmation opened from a Dialog's confirm button, as the creation assistant does. */
function Harness({ handlers, replace, cancel }: { handlers: Handlers; replace: () => void; cancel: () => void }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <FullPageModal isOpen onClose={handlers.formClose ?? vi.fn()} id="form">
      <DialogPrimitive
        open
        title="Assistant"
        confirmLabel="Apply"
        onConfirm={() => {
          handlers.dialogConfirm?.();
          setConfirmOpen(true);
        }}
        onCancel={handlers.dialogCancel ?? vi.fn()}
      >
        body
      </DialogPrimitive>
      <ConfirmationDialog
        open={confirmOpen}
        title="Replace?"
        confirmLabel="Replace"
        criticalAction
        onConfirm={replace}
        onCancel={() => {
          cancel();
          setConfirmOpen(false);
        }}
      />
    </FullPageModal>
  );
}

function renderOverDialog(handlers: Handlers) {
  const replace = vi.fn();
  const cancel = vi.fn();
  act(() => root.render(<Harness handlers={handlers} replace={replace} cancel={cancel} />));
  const apply = buttonIn(document, "Apply");
  act(() => apply.focus());
  act(() => apply.click());
  return { apply, replace, cancel };
}

describe("ConfirmationDialog keyboard", () => {
  it("focuses Cancel, the safe choice, on open", () => {
    renderOverDialog({});
    expect(document.activeElement).toBe(buttonIn(confirmation(), "Cancel"));
  });

  it("keeps Tab inside itself instead of the Dialog underneath", () => {
    renderOverDialog({});
    const cancelButton = buttonIn(confirmation(), "Cancel");
    const replaceButton = buttonIn(confirmation(), "Replace");

    // Native Tab moves Cancel → Replace: neither dialog may pull focus back.
    expect(press("Tab").defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(cancelButton);
    // Wrapping is handled by the confirmation, in both directions.
    press("Tab", { shiftKey: true });
    expect(document.activeElement).toBe(replaceButton);
    press("Tab");
    expect(document.activeElement).toBe(cancelButton);
  });

  it("Enter on Replace runs the confirmation only, never the Dialog's confirm", () => {
    const dialogConfirm = vi.fn();
    const { replace } = renderOverDialog({ dialogConfirm });
    const replaceButton = buttonIn(confirmation(), "Replace");
    act(() => replaceButton.focus());
    press("Enter");
    // The browser turns Enter / Space on a focused button into a click.
    act(() => replaceButton.click());
    expect(replace).toHaveBeenCalledTimes(1);
    expect(dialogConfirm).toHaveBeenCalledTimes(1); // the click that opened the confirmation
  });

  it("Escape closes only the confirmation and gives focus back to its opener", () => {
    const dialogCancel = vi.fn();
    const formClose = vi.fn();
    const { apply, cancel } = renderOverDialog({ dialogCancel, formClose });
    press("Escape");
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(dialogCancel).not.toHaveBeenCalled();
    expect(formClose).not.toHaveBeenCalled();
    expect(confirmation()).toBeNull();
    expect(document.activeElement).toBe(apply);
  });
});
