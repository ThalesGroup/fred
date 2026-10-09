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

// Coverage for click-to-close on the "scrim" backdrop (PromptViewDialog
// follow-up): only "scrim" is dismissible by clicking outside the card — the
// opaque "main"/"container" full-page takeovers used by data-entry forms
// must NOT close on a stray backdrop click.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FullPageModal } from "./FullPageModal";
import { DialogPrimitive } from "../Dialog/DialogPrimitive";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("FullPageModal backdrop click", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  const render = (background: "main" | "container" | "scrim" | undefined, onClose: () => void) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <FullPageModal isOpen onClose={onClose} id="test-modal" background={background}>
          <div data-testid="card">card content</div>
        </FullPageModal>,
      );
    });
  };

  it("closes on a scrim click outside the card", () => {
    const onClose = vi.fn();
    render("scrim", onClose);

    const dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    act(() => {
      dialog.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close when the click lands on the card itself", () => {
    const onClose = vi.fn();
    render("scrim", onClose);

    const card = document.querySelector('[data-testid="card"]') as HTMLElement;
    act(() => {
      card.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not close on a backdrop click for the opaque 'main' background", () => {
    const onClose = vi.fn();
    render("main", onClose);

    const dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    act(() => {
      dialog.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("FullPageModal Escape", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    document.getElementById("modal-portal")?.remove();
  });

  const render = (onClose: () => void, nested?: { onCancel: () => void }) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <FullPageModal isOpen onClose={onClose} id="test-modal">
          <div>form</div>
          {nested && (
            <DialogPrimitive open title="Nested" confirmLabel="OK" onConfirm={() => {}} onCancel={nested.onCancel}>
              nested content
            </DialogPrimitive>
          )}
        </FullPageModal>,
      );
    });
  };

  const pressEscape = () => {
    act(() => {
      (document.activeElement ?? document.body).dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }),
      );
    });
  };

  it("closes when it is the only modal", () => {
    const onClose = vi.fn();
    render(onClose);
    pressEscape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("leaves Escape to a dialog opened over it", () => {
    const onClose = vi.fn();
    const onCancel = vi.fn();
    render(onClose, { onCancel });
    pressEscape();
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("treats an alertdialog opened over it as the topmost modal", () => {
    const onClose = vi.fn();
    render(onClose);
    const alert = document.createElement("div");
    alert.setAttribute("role", "alertdialog");
    alert.setAttribute("aria-modal", "true");
    document.body.appendChild(alert);
    pressEscape();
    alert.remove();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("ignores an Escape another handler already consumed", () => {
    const onClose = vi.fn();
    render(onClose);
    const consume = (event: KeyboardEvent) => event.preventDefault();
    window.addEventListener("keydown", consume, { capture: true });
    pressEscape();
    window.removeEventListener("keydown", consume, { capture: true });
    expect(onClose).not.toHaveBeenCalled();
  });
});
