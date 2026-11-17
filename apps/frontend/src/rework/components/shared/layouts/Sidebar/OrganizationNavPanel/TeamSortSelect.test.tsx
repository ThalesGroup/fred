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
import TeamSortSelect from "./TeamSortSelect";

const options = [
  { value: "recent", label: "Recent" },
  { value: "alpha", label: "A to Z" },
];

it("opens the sort listbox from its icon button and picks an order", () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.append(container);
  const onChange = vi.fn();
  const root = createRoot(container);
  act(() => root.render(<TeamSortSelect value="recent" options={options} onChange={onChange} ariaLabel="Sort" />));
  const trigger = container.querySelector<HTMLButtonElement>('button[aria-label="Sort"]')!;
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  act(() => trigger.click());
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  const selected = container.querySelector('[role="option"][aria-selected="true"]');
  expect(selected?.textContent).toBe("Recent");
  act(() => container.querySelectorAll<HTMLButtonElement>('[role="option"]')[1].click());
  expect(onChange).toHaveBeenCalledWith("alpha");
  expect(container.querySelector('[role="listbox"]')).toBeNull();
  act(() => root.unmount());
  container.remove();
});
