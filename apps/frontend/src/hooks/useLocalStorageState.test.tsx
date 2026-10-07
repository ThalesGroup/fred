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
import { expect, it, vi } from "vitest";
import { useLocalStorageState } from "./useLocalStorageState";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("keeps React state usable when an iframe cannot access localStorage", () => {
  const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage");
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get: () => {
      throw new DOMException("Storage denied", "SecurityError");
    },
  });
  const container = document.createElement("div");
  const root = createRoot(container);
  function Probe() {
    const [value, setValue] = useLocalStorageState<number | undefined>("restricted", 320);
    return (
      <>
        <output>{value ?? "cleared"}</output>
        <button onClick={() => setValue(400)}>Resize</button>
        <button onClick={() => setValue(undefined)}>Clear</button>
      </>
    );
  }
  try {
    act(() => root.render(<Probe />));
    expect(container.querySelector("output")?.textContent).toBe("320");
    act(() => container.querySelectorAll("button")[0].click());
    expect(container.querySelector("output")?.textContent).toBe("400");
    act(() => container.querySelectorAll("button")[1].click());
    expect(container.querySelector("output")?.textContent).toBe("cleared");
  } finally {
    act(() => root.unmount());
    if (descriptor) Object.defineProperty(window, "localStorage", descriptor);
    else Reflect.deleteProperty(window, "localStorage");
    warn.mockRestore();
  }
});
