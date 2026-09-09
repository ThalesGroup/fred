// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { act, createRef } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import TextInput from "./TextInput.tsx";

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

function input() {
  const element = container.querySelector("input");
  if (!element) throw new Error("input not rendered");
  return element;
}

describe("TextInput native and accessible behavior", () => {
  it("preserves caller id, ref, handler, and native props", () => {
    const ref = createRef<HTMLInputElement>();
    const onChange = vi.fn();
    render(
      <TextInput
        id="account-name"
        ref={ref}
        label="Account"
        type="email"
        autoComplete="email"
        name="account"
        onChange={onChange}
      />,
    );
    expect(container.querySelector("label")?.htmlFor).toBe("account-name");
    expect(ref.current).toBe(input());
    expect(input().type).toBe("email");
    expect(input().autocomplete).toBe("email");
    expect(input().name).toBe("account");
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input(), "a@example.test");
      input().dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(onChange).toHaveBeenCalledOnce();
  });

  it("merges caller and help descriptions", () => {
    render(<TextInput id="topic" label="Topic" explanation="Helpful text" aria-describedby="outside" />);
    const ids = input().getAttribute("aria-describedby")?.split(" ");
    expect(ids).toEqual(["outside", "topic-description"]);
    expect(document.getElementById("topic-description")?.textContent).toBe("Helpful text");
  });

  it.each([
    ["help", { explanation: "Compact help" }],
    ["error", { error: "Compact error" }],
  ])("keeps compact %s text in the accessible description", (_kind, messageProps) => {
    render(<TextInput id="compact-topic" compact {...messageProps} />);
    expect(input().getAttribute("aria-describedby")).toBe("compact-topic-description");
    expect(document.getElementById("compact-topic-description")?.textContent).toBe(Object.values(messageProps)[0]);
  });

  it("marks only enabled errors invalid", () => {
    render(<TextInput id="topic" error="Required" />);
    expect(input().getAttribute("aria-invalid")).toBe("true");
    expect(input().getAttribute("aria-describedby")).toBe("topic-description");
  });

  it("does not impose invalid state for a disabled error", () => {
    render(<TextInput error="Required" disabled />);
    expect(input().hasAttribute("aria-invalid")).toBe(false);
  });

  it("counts controlled values without stringifying absence", () => {
    render(<TextInput value="fred" onChange={() => undefined} maxLength={10} />);
    expect(container.textContent).toContain("4 / 10");
  });

  it("counts an uncontrolled default and subsequent edits", () => {
    render(<TextInput defaultValue="fred" maxLength={10} />);
    expect(container.textContent).toContain("4 / 10");
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input(), "frontend");
      input().dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("8 / 10");
  });
});
