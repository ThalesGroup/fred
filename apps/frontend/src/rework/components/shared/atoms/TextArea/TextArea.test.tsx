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
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import TextArea, { type TextAreaProps } from "./TextArea";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("counts controlled text and empty values", () => {
  expect(renderToStaticMarkup(<TextArea label="Notes" value="abc" readOnly maxLength={100} />)).toContain("3 / 100");
  expect(renderToStaticMarkup(<TextArea label="Notes" value="" readOnly maxLength={100} />)).toContain("0 / 100");
});

it.each([{ defaultValue: "abc" }, {}, { value: "abc", defaultValue: "abc" }])(
  "rejects uncontrolled or mixed props from untyped consumers: %j",
  (values) => {
    const props = { label: "Notes", maxLength: 100, ...values } as TextAreaProps;
    expect(() => renderToStaticMarkup(<TextArea {...props} />)).toThrow("TextArea requires a controlled value");
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
