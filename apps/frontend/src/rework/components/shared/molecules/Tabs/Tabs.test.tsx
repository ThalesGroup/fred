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
import { afterEach, describe, expect, it, vi } from "vitest";
import Tabs from "./Tabs.tsx";

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
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

const tabs = [
  { value: "corpus", label: "Corpus" },
  { value: "mine", label: "Espace perso" },
  { value: "shared", label: "Espace partagé" },
  { value: "agents", label: "Agents" },
];

describe("Tabs", () => {
  it("renders every tab and marks only the active one selected", () => {
    render(<Tabs tabs={tabs} value="mine" onChange={vi.fn()} />);
    const buttons = Array.from(container.querySelectorAll('[role="tab"]'));
    expect(buttons).toHaveLength(4);
    expect(buttons.map((b) => b.getAttribute("aria-selected"))).toEqual(["false", "true", "false", "false"]);
  });

  it("calls onChange with the clicked tab's value", () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} value="corpus" onChange={onChange} />);
    const buttons = Array.from(container.querySelectorAll('[role="tab"]'));
    click(buttons[2]);
    expect(onChange).toHaveBeenCalledWith("shared");
  });
});
