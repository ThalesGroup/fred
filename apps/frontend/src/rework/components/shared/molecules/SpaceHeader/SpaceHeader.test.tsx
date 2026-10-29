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
import { describe, expect, it, vi } from "vitest";
import SpaceHeader from "./SpaceHeader";

const render = (node: React.ReactNode) => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div");
  const root = createRoot(host);
  act(() => root.render(node));
  return { host, unmount: () => act(() => root.unmount()) };
};

describe("SpaceHeader", () => {
  it("is a read-only heading with the space on a small line", () => {
    const { host, unmount } = render(<SpaceHeader eyebrow="Acme" title="Home" />);
    expect(host.querySelector("h2")?.textContent).toBe("Home");
    expect(host.querySelector("h2")?.previousElementSibling?.textContent).toBe("Acme");
    expect(host.querySelector("button")).toBeNull();
    unmount();
  });

  it("drops the small line without a space", () => {
    const { host, unmount } = render(<SpaceHeader title="Home" />);
    expect(host.querySelector("h2")?.previousElementSibling).toBeNull();
    unmount();
  });

  it("keeps the heading around the menu trigger and reports its state", () => {
    const onToggle = vi.fn();
    const { host, unmount } = render(
      <SpaceHeader eyebrow="Acme" title="Administration" menu={{ open: false, onToggle }}>
        <p>menu</p>
      </SpaceHeader>,
    );
    const button = host.querySelector("h2 > button")!;
    expect(button.getAttribute("aria-haspopup")).toBe("menu");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.textContent).toContain("Administration");
    act(() => (button as HTMLButtonElement).click());
    expect(onToggle).toHaveBeenCalledOnce();
    expect(host.textContent).toContain("menu");
    unmount();
  });
});
