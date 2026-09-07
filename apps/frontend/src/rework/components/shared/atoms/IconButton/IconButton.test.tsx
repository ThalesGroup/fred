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

// Coverage for the `loading` prop (added for RFC KNOWLEDGE-WORKSPACE-REWORK-RFC.md
// §13.13's bulk download): a slow async action must read as "in progress",
// not dead/unresponsive — `loading` swaps the icon for a spinner and
// disables the button.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import IconButton from "./IconButton.tsx";

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

function button(): HTMLButtonElement {
  const el = container.querySelector("button");
  if (!el) throw new Error("button not rendered");
  return el;
}

function spinner(): SVGElement | null {
  return container.querySelector('svg[role="status"]');
}

function badge(): HTMLElement | null {
  // The badge is the only aria-hidden span the button renders.
  return container.querySelector('span[aria-hidden="true"]');
}

describe("IconButton badge", () => {
  const base = { variant: "icon", size: "small", icon: { category: "outlined", type: "attach_file" } } as const;

  it("renders no badge and no wrapper when badgeCount is omitted", () => {
    // Every existing call site must keep rendering a bare <button>.
    render(<IconButton {...base} aria-label="Attachments" />);

    expect(badge()).toBeNull();
    expect(container.firstElementChild?.tagName).toBe("BUTTON");
  });

  it("renders no badge at zero", () => {
    // An empty conversation gets a plain button, not a "0" pill.
    render(<IconButton {...base} aria-label="Attachments" badgeCount={0} />);

    expect(badge()).toBeNull();
  });

  it("shows the count from one upward", () => {
    render(<IconButton {...base} aria-label="Attachments" badgeCount={1} />);

    expect(badge()?.textContent).toBe("1");
  });

  it("caps the label at 999+", () => {
    render(<IconButton {...base} aria-label="Attachments" badgeCount={1000} />);

    expect(badge()?.textContent).toBe("999+");
  });

  it("shows 999 itself unabbreviated", () => {
    render(<IconButton {...base} aria-label="Attachments" badgeCount={999} />);

    expect(badge()?.textContent).toBe("999");
  });

  it("keeps the badge out of the accessible name", () => {
    // aria-hidden: the caller's label carries the count, so a screen reader
    // does not read a bare digit after the button name.
    render(<IconButton {...base} aria-label="Attachments (3)" badgeCount={3} />);

    expect(badge()?.getAttribute("aria-hidden")).toBe("true");
    expect(button().getAttribute("aria-label")).toBe("Attachments (3)");
  });
});

describe("IconButton loading state", () => {
  it("shows the icon, not a spinner, and stays enabled when loading is omitted/false", () => {
    render(
      <IconButton
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        aria-label="Download"
      />,
    );

    expect(spinner()).toBeNull();
    expect(button().disabled).toBe(false);
    expect(button().getAttribute("aria-busy")).toBe("false");
  });

  it("shows a spinner instead of the icon and disables the button when loading", () => {
    render(
      <IconButton
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        aria-label="Download"
        loading
      />,
    );

    expect(spinner()).not.toBeNull();
    expect(button().disabled).toBe(true);
    expect(button().getAttribute("aria-busy")).toBe("true");
  });

  it("does not fire onClick while loading (native disabled semantics)", () => {
    const onClick = vi.fn();
    render(
      <IconButton
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        aria-label="Download"
        loading
        onClick={onClick}
      />,
    );

    act(() => {
      button().dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(onClick).not.toHaveBeenCalled();
  });

  it("stays disabled if the caller also passes disabled explicitly, independent of loading", () => {
    render(
      <IconButton
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        aria-label="Download"
        disabled
      />,
    );

    expect(button().disabled).toBe(true);
    expect(spinner()).toBeNull(); // disabled alone, not loading — icon still shows
  });
});
