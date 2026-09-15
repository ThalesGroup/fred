// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import Button from "./Button.tsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("Button", () => {
  it("retains native button behavior and caller classes", () => {
    const onClick = vi.fn();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() =>
      root.render(
        <Button color="primary" variant="filled" size="medium" className="consumer-class" onClick={onClick}>
          Continue
        </Button>,
      ),
    );
    const button = container.querySelector("button")!;
    act(() => button.click());
    expect(button.classList.contains("consumer-class")).toBe(true);
    expect(onClick).toHaveBeenCalledOnce();
  });
});
