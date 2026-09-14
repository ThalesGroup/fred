// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import Icon, { MaterialIcon } from "./Icon.tsx";

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

describe("Icon accessibility", () => {
  it("is decorative by default", () => {
    render(<MaterialIcon type="search" />);
    expect(container.querySelector("span")?.getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector("span")?.hasAttribute("aria-label")).toBe(false);
  });

  it("uses only a caller-owned informative name", () => {
    render(<MaterialIcon type="search" accessibleName="Search results" />);
    const icon = container.querySelector("span");
    expect(icon?.getAttribute("role")).toBe("img");
    expect(icon?.getAttribute("aria-label")).toBe("Search results");
  });

  it("retains custom-icon compatibility without deriving a name", () => {
    render(<Icon category="outlined" type="customAgent" />);
    const icon = container.querySelector("span");
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    expect(icon?.hasAttribute("aria-label")).toBe(false);
  });
});
