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

import { act, useState } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import TextArea, { type TextAreaProps } from "./TextArea";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("counts controlled text and empty values", () => {
  expect(renderToStaticMarkup(<TextArea label="Notes" value="abc" readOnly maxLength={100} />)).toContain("3 / 100");
  expect(renderToStaticMarkup(<TextArea label="Notes" value="" readOnly maxLength={100} />)).toContain("0 / 100");
});

it.each([{ value: null }, { value: "abc", defaultValue: "abc" }])(
  "rejects null controlled or mixed props from untyped consumers: %j",
  (values) => {
    const props = { label: "Notes", maxLength: 100, ...values } as TextAreaProps;
    expect(() => renderToStaticMarkup(<TextArea {...props} />)).toThrow(
      "TextArea: use either a non-null controlled value or defaultValue, not both.",
    );
  },
);

it("updates the counter through the caller's change handler and external reset", () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const changed = vi.fn();
  function Form() {
    const [value, setValue] = useState("abc");
    return (
      <>
        <TextArea
          label="Notes"
          value={value}
          maxLength={100}
          onChange={(event) => {
            changed(event.currentTarget.value);
            setValue(event.currentTarget.value);
          }}
        />
        <button onClick={() => setValue("")}>Reset</button>
      </>
    );
  }
  try {
    act(() => root.render(<Form />));
    const textarea = container.querySelector("textarea")!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(textarea, "abcdef");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(changed).toHaveBeenCalledWith("abcdef");
    expect(container.textContent).toContain("6 / 100");
    act(() => container.querySelector("button")!.click());
    expect(textarea.value).toBe("");
    expect(container.textContent).toContain("0 / 100");
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});

it.each([undefined, "notes"])("associates the label with its textarea for id %s", (id) => {
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(<TextArea id={id} label="Notes" value="" readOnly />);
  const textarea = container.querySelector("textarea")!;
  expect(textarea.id).not.toBe("");
  if (id) expect(textarea.id).toBe(id);
  expect(container.querySelector("label")!.htmlFor).toBe(textarea.id);
});

it("rejects an implicitly frozen controlled field", () => {
  const props = { label: "Notes", value: "abc" } as TextAreaProps;
  expect(() => renderToStaticMarkup(<TextArea {...props} />)).toThrow(
    "TextArea requires onChange, readOnly or disabled",
  );
});
it("accepts explicit disabled mode without a change handler", () => {
  expect(renderToStaticMarkup(<TextArea label="Notes" value="abc" disabled />)).toContain("disabled");
});

it("preserves native uncontrolled editing, refs and form reset with an accurate counter", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const ref = { current: null as HTMLTextAreaElement | null };
  const changed = vi.fn();
  try {
    act(() =>
      root.render(
        <form>
          <TextArea label="Notes" defaultValue="Bonjour" maxLength={100} ref={ref} onChange={changed} />
        </form>,
      ),
    );
    const textarea = container.querySelector("textarea")!;
    expect(ref.current).toBe(textarea);
    expect(textarea.value).toBe("Bonjour");
    expect(container.textContent).toContain("7 / 100");
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(textarea, "Bonsoir!");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(changed).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("8 / 100");
    const form = container.querySelector("form")!;
    await act(async () => {
      form.reset();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(textarea.value).toBe("Bonjour");
    expect(container.textContent).toContain("7 / 100");
  } finally {
    act(() => root.unmount());
    expect(ref.current).toBeNull();
    container.remove();
  }
});
it("supports an initially empty uncontrolled field", () => {
  expect(renderToStaticMarkup(<TextArea label="Notes" maxLength={100} />)).toContain("0 / 100");
});

it("associates dynamic errors and hints without losing caller descriptions", () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    const render = (error?: string) =>
      act(() =>
        root.render(
          <TextArea
            label="Email"
            defaultValue=""
            explanation="Use your work email"
            error={error}
            aria-describedby="external-help"
          />,
        ),
      );
    render();
    const field = host.querySelector("textarea")!;
    const descriptions = () => field.getAttribute("aria-describedby")!.split(" ");
    expect(descriptions()[0]).toBe("external-help");
    const hint = host.querySelector('[aria-live="polite"]')!;
    expect(descriptions()).toContain(hint.id);
    expect(hint.textContent).toBe("Use your work email");
    render("Invalid email");
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(hint.textContent).toBe("Invalid email");
    render();
    expect(field.hasAttribute("aria-invalid")).toBe(false);
    expect(hint.textContent).toBe("Use your work email");
  } finally {
    act(() => root.unmount());
  }
});

it("keeps an initially empty live region mounted across error updates", () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    const render = (error?: string) => act(() => root.render(<TextArea label="Notes" error={error} />));
    render();
    const live = host.querySelector('[aria-live="polite"]')!;
    expect(live).not.toBeNull();
    expect(live.textContent).toBe("");
    for (const error of ["Required", undefined, "Too short"]) {
      render(error);
      expect(host.querySelector('[aria-live="polite"]')).toBe(live);
      expect(live.textContent).toBe(error ?? "");
      expect(live.closest('[hidden], [aria-hidden="true"]')).toBeNull();
      expect(host.querySelector("textarea")!.getAttribute("aria-describedby")).toBe(error ? live.id : null);
    }
  } finally {
    act(() => root.unmount());
  }
});

it("renders a zero-character limit", () => {
  expect(renderToStaticMarkup(<TextArea label="Notes" maxLength={0} />)).toContain("0 / 0");
});
it.each([false, true])("synchronizes a reset with synchronous parent updates, canceled=%s", async (cancel) => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  function Form() {
    const [version, setVersion] = useState(0);
    return (
      <form
        onReset={(event) => {
          if (cancel) event.preventDefault();
          flushSync(() => setVersion((value) => value + 1));
        }}
      >
        <TextArea label={`Notes ${version}`} defaultValue="abc" maxLength={100} />
      </form>
    );
  }
  try {
    act(() => root.render(<Form />));
    const field = host.querySelector("textarea")!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, "abcdef");
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(host.textContent).toContain("6 / 100");
    await act(async () => {
      // happy-dom reset() ignores preventDefault; dispatch the canceled path explicitly.
      const form = host.querySelector("form")!;
      if (cancel) expect(form.dispatchEvent(new Event("reset", { bubbles: true, cancelable: true }))).toBe(false);
      else form.reset();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(field.value).toBe(cancel ? "abcdef" : "abc");
    expect(host.textContent).toContain(cancel ? "6 / 100" : "3 / 100");
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
