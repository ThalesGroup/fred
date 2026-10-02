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

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { IndicatorDot } from "./IndicatorDot";

it.each([undefined, ""])("keeps an unlabeled dot decorative (%s)", (label) => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<IndicatorDot status="active" label={label} />);
  expect(host.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  expect(host.querySelector('[role="img"]')).toBeNull();
});
it("announces the caller's localized label", () => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<IndicatorDot status="active" label="Évaluation active" />);
  expect(host.querySelector('[role="img"]')?.getAttribute("aria-label")).toBe("Évaluation active");
  expect(host.firstElementChild?.hasAttribute("aria-hidden")).toBe(false);
});
