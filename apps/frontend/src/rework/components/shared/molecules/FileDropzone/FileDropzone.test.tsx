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
import FileDropzone from "./FileDropzone.tsx";

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

describe("FileDropzone", () => {
  it("ties a displayed error to the upload control and announces it", () => {
    render(<FileDropzone accept=".json" hint="Upload" onFile={vi.fn()} error="Invalid JSON" />);
    const zone = container.querySelector("button")!;
    const error = container.querySelector('[role="alert"]')!;
    expect(error.textContent).toBe("Invalid JSON");
    expect(zone.getAttribute("aria-describedby")).toBe(error.id);
    expect(zone.getAttribute("aria-invalid")).toBe("true");
  });

  it("clears the input so the same file can be picked again", () => {
    const onFile = vi.fn();
    render(<FileDropzone accept=".json" hint="Upload" onFile={onFile} />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["{}"], "suite.json");
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    act(() => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onFile).toHaveBeenCalledExactlyOnceWith(file);
    expect(input.value).toBe("");
  });
});
