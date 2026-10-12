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
import DuplicateAgentDialog from "./DuplicateAgentDialog";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/utils/Portal.tsx", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@shared/utils/Portal.tsx")>()),
  Portal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const TAKEN = new Set(["analyst", "writer"]);
const onConfirm = vi.fn();
let container: HTMLDivElement;
let root: Root;

function render(initialName: string) {
  act(() => {
    root.render(
      <DuplicateAgentDialog
        open
        initialName={initialName}
        takenNames={TAKEN}
        onCancel={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
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
  onConfirm.mockReset();
});

const input = () => container.querySelector("input") as HTMLInputElement;
const confirmButton = () =>
  Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("duplicateDialog.confirm"),
  ) as HTMLButtonElement;
const takenMessage = () => container.textContent?.includes("rework.teams.formAgent.fields.name.taken");

function type(value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function leaveField() {
  act(() => {
    input().dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  });
}

describe("duplicating under a taken name", () => {
  it("says nothing while typing, then warns and disables Duplicate on leaving the field", () => {
    render("Analyst (2)");
    type(" WRITER ");
    expect(takenMessage()).toBe(false);
    expect(confirmButton().disabled).toBe(false);

    leaveField();

    expect(takenMessage()).toBe(true);
    expect(confirmButton().disabled).toBe(true);
  });

  it("re-enables Duplicate once the name is changed to a free one", () => {
    render("Analyst (2)");
    type("writer");
    leaveField();
    type("Writer 2");
    leaveField();

    expect(takenMessage()).toBe(false);
    expect(confirmButton().disabled).toBe(false);
  });

  it("checks on Enter too, without duplicating", () => {
    render("Analyst (2)");
    type("analyst");
    act(() => {
      input().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });

    expect(takenMessage()).toBe(true);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("duplicates under a free name", () => {
    render("Analyst (2)");
    act(() => confirmButton().click());

    expect(onConfirm).toHaveBeenCalledWith("Analyst (2)");
  });
});
