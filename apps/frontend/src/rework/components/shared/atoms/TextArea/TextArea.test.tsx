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
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import TextArea from "./TextArea.tsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(ui));
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("TextArea description", () => {
  it("shows the description between the label and the field, and ties it to the field", () => {
    render(<TextArea label="Team description" description="State the team's objectives." value="" readOnly />);

    const [label, description, field] = Array.from(container.firstElementChild!.children);
    expect(label.tagName).toBe("LABEL");
    expect(description.textContent).toBe("State the team's objectives.");
    expect(field.tagName).toBe("TEXTAREA");
    expect(field.getAttribute("aria-describedby")).toBe(description.id);
  });

  it("adds nothing when no description is given", () => {
    render(<TextArea label="Notes" value="" readOnly />);

    expect(container.querySelector("textarea")?.hasAttribute("aria-describedby")).toBe(false);
    expect(container.firstElementChild!.children).toHaveLength(2);
  });
});
