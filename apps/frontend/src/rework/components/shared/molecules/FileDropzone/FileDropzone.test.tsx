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
import FileDropzone from "./FileDropzone";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it("associates a dynamic upload error and removes invalid state after recovery", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  const render = (error?: string) =>
    act(() => root.render(<FileDropzone accept=".csv" hint="Upload" onFile={vi.fn()} error={error} />));
  try {
    render();
    expect(container.querySelector("button")!.hasAttribute("aria-invalid")).toBe(false);
    render("Invalid CSV");
    const error = container.querySelector('[role="alert"]')!;
    expect(error.textContent).toBe("Invalid CSV");
    for (const control of container.querySelectorAll("button, input")) {
      expect(control.getAttribute("aria-describedby")).toBe(error.id);
      expect(control.getAttribute("aria-invalid")).toBe("true");
    }
    render();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    for (const control of container.querySelectorAll("button, input")) {
      expect(control.hasAttribute("aria-describedby")).toBe(false);
      expect(control.hasAttribute("aria-invalid")).toBe(false);
    }
  } finally {
    act(() => root.unmount());
  }
});
