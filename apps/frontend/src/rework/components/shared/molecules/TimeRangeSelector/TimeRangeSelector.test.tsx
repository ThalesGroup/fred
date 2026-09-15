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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TimeRangeSelector from "./TimeRangeSelector";
import { resolvePreset, type TimeRange } from "./timeRange.types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en-US" } }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
const onChange = vi.fn();

function render(value: TimeRange) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TimeRangeSelector value={value} onChange={onChange} />);
  });
}

const button = (label: string) => container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
const click = (el: HTMLElement) => act(() => el.click());
const openDropdown = () => click(container.querySelector<HTMLButtonElement>('button[aria-haspopup="true"]')!);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 8, 16, 15, 30));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  onChange.mockReset();
  vi.useRealTimers();
});

describe("TimeRangeSelector", () => {
  it("steps back to the previous month and cannot step past the current one", () => {
    render(resolvePreset("thisMonth"));
    expect(button("rework.analytics.timeRange.next").disabled).toBe(true);

    click(button("rework.analytics.timeRange.previous"));
    expect(onChange).toHaveBeenCalledWith(resolvePreset("thisMonth", -1));
  });

  it("labels a shifted month by its name and lets it step forward again", () => {
    render(resolvePreset("thisMonth", -1));
    expect(container.textContent).toContain("August 2026");
    expect(button("rework.analytics.timeRange.next").disabled).toBe(false);
  });

  it("labels a shifted rolling window by its dates, with the year only outside the current one", () => {
    render(resolvePreset("last30d", -1));
    expect(container.textContent).toContain("Jul 18 – Aug 17");

    act(() => root.unmount());
    container.remove();
    render(resolvePreset("last30d", -12));
    expect(container.textContent).toMatch(/2025 – .*2025/);
  });

  it("closes the dropdown when stepping, so its custom dates never go stale", () => {
    render(resolvePreset("thisMonth", -1));
    openDropdown();
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();

    click(button("rework.analytics.timeRange.next"));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(onChange).toHaveBeenCalledWith(resolvePreset("thisMonth"));
  });

  it("no longer offers the sub-day presets", () => {
    render(resolvePreset("last30d"));
    openDropdown();
    expect(container.textContent).not.toContain("rework.analytics.presets.last15m");
    expect(container.textContent).toContain("rework.analytics.presets.last24h");
  });

  it("shows each year once on the month timeline and selects a past month", () => {
    render(resolvePreset("last30d"));
    openDropdown();

    const years = [...container.querySelectorAll('[role="group"] span')].map((el) => el.textContent);
    expect(years).toEqual(["2024", "2025", "2026"]);

    click(button("December 2025"));
    expect(onChange).toHaveBeenCalledWith(resolvePreset("thisMonth", -9));
  });

  it("marks the selected month as pressed", () => {
    render(resolvePreset("thisMonth", -9));
    openDropdown();
    expect(button("December 2025").getAttribute("aria-pressed")).toBe("true");
    expect(button("September 2026").getAttribute("aria-pressed")).toBe("false");
  });
});
