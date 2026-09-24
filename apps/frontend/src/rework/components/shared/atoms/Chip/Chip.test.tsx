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
import Chip from "./Chip";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("keeps its content slots and gives the removal action a caller-owned or safe default name", () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const onRemove = vi.fn();
  act(() =>
    root.render(
      <Chip
        label="Draft"
        secondary="Ready"
        leading={<span>Icon</span>}
        trailing={<span>Trailing</span>}
        tone="error"
        onRemove={onRemove}
      />,
    ),
  );
  expect(host.textContent).toContain("Draft");
  expect(host.textContent).toContain("Ready");
  expect(host.textContent).toContain("Trailing");
  const remove = host.querySelector("button") as HTMLButtonElement;
  expect(remove.getAttribute("aria-label")).toBe("Remove Draft");
  act(() => remove.click());
  expect(onRemove).toHaveBeenCalledTimes(1);
  act(() => root.render(<Chip label="Draft" onRemove={onRemove} removeAriaLabel="Delete draft selection" />));
  expect(host.querySelector("button")?.getAttribute("aria-label")).toBe("Delete draft selection");
  act(() => root.unmount());
  host.remove();
});
