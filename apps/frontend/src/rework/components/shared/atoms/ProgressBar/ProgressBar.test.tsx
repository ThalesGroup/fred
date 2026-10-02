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
import { describe, expect, it } from "vitest";
import ProgressBar from "./ProgressBar";

describe("ProgressBar bounds", () => {
  it.each([
    [30, 100, 30, 100, 30],
    [-5, 100, 0, 100, 0],
    [120, 100, 100, 100, 100],
    [Infinity, 100, 100, 100, 100],
    [-Infinity, 100, 0, 100, 0],
    [NaN, 100, 0, 100, 0],
    [30, 0, 0, 0, 0],
    [30, -10, 0, 0, 0],
    [30, NaN, 0, 0, 0],
    [30, Infinity, 0, 0, 0],
  ])("aligns current %s / max %s with visual and accessible bounds", (current, max, now, upper, percent) => {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(
      <ProgressBar theme="primary" current={current} max={max} aria-label="Progress" />,
    );
    const bar = container.querySelector('[role="progressbar"]')!;
    expect(bar.getAttribute("aria-valuenow")).toBe(String(now));
    expect(bar.getAttribute("aria-valuemax")).toBe(String(upper));
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect((bar.firstElementChild as HTMLElement).style.width).toBe(`${percent}%`);
  });
});

it("rejects missing names from untyped callers", () => {
  // @ts-expect-error public props require a name
  const unnamed = <ProgressBar theme="primary" current={3} max={10} />;
  expect(() => renderToStaticMarkup(unnamed)).toThrow("accessible name");
});
it("accepts a visible label reference", () => {
  expect(
    renderToStaticMarkup(<ProgressBar theme="primary" current={3} max={10} aria-labelledby="task-label" />),
  ).toContain('aria-labelledby="task-label"');
});
