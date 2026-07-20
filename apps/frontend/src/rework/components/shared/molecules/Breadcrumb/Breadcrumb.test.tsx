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
import { Breadcrumb, type BreadcrumbSegment } from "./Breadcrumb.tsx";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(segments: BreadcrumbSegment[]) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<Breadcrumb segments={segments} />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function click(el: HTMLElement) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("Breadcrumb", () => {
  it("renders every non-last segment as a clickable button and the last as non-interactive current text", () => {
    const onClickA = vi.fn();
    const onClickB = vi.fn();
    render([{ label: "Evaluations", onClick: onClickA }, { label: "Run 12", onClick: onClickB }, { label: "Case 3" }]);

    const buttons = container.querySelectorAll("button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0].textContent).toBe("Evaluations");
    expect(buttons[1].textContent).toBe("Run 12");

    const current = container.querySelector('[aria-current="page"]');
    expect(current).not.toBeNull();
    expect(current?.tagName).not.toBe("BUTTON");
    expect(current?.textContent).toBe("Case 3");
  });

  it("clicking a non-last segment fires its onClick exactly once", () => {
    const onClickA = vi.fn();
    render([{ label: "Evaluations", onClick: onClickA }, { label: "Run 12" }]);

    const [first] = container.querySelectorAll("button");
    click(first);

    expect(onClickA).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for an empty segment list", () => {
    render([]);
    expect(container.querySelector("nav")).toBeNull();
  });

  it("exposes an accessible nav landmark labelled Breadcrumb", () => {
    render([{ label: "Evaluations" }]);
    const nav = container.querySelector("nav");
    expect(nav?.getAttribute("aria-label")).toBe("Breadcrumb");
  });
});
