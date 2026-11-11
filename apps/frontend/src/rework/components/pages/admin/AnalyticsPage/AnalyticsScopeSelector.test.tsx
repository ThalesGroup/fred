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

const h = vi.hoisted(() => ({
  rows: [
    { team_id: "t-a", name: "Alpha", member_count: 12 },
    { team_id: "t-b", name: "Beta", member_count: 2 },
    { team_id: "t-c", name: "Gamma", member_count: 1 },
    { team_id: "t-d", name: "Delta", member_count: 3 },
    { team_id: "t-e", name: "Epsilon", member_count: 4 },
    { team_id: "t-f", name: "Zeta", member_count: 5 },
  ],
  catalog: vi.fn(),
  adoption: vi.fn(() => ({ data: { people_with_access: 20 } })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => (options?.count !== undefined ? `${key}:${options.count}` : key),
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnalyticsTeamsCatalogQuery: () => h.catalog(),
  useAnalyticsAdoptionQuery: h.adoption,
}));

import AnalyticsScopeSelector, { AnalyticsScopeSummary, orderScopeRows } from "./AnalyticsScopeSelector";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root | undefined;

function render(node: React.ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(node));
}

beforeEach(() => {
  h.catalog.mockReturnValue({ data: { rows: h.rows } });
});

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  container?.remove();
});

const trigger = () => container.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!;
const button = (label: string) => [...container.querySelectorAll("button")].find((el) => el.textContent === label)!;
const rowNames = () =>
  [...container.querySelectorAll('[role="dialog"] label')].map((el) => el.textContent ?? "").filter((t) => t);
const tick = (name: string) => {
  const row = [...container.querySelectorAll('[role="dialog"] label')].find((el) => el.textContent?.includes(name))!;
  act(() => row.querySelector("input")!.click());
};

describe("orderScopeRows", () => {
  it("puts the applied selection first and filters by name", () => {
    const { selected, others } = orderScopeRows(h.rows, ["t-c"], "");
    expect(selected.map((r) => r.name)).toEqual(["Gamma"]);
    expect(others.map((r) => r.name)).toEqual(["Alpha", "Beta", "Delta", "Epsilon", "Zeta"]);
    expect(orderScopeRows(h.rows, [], " ALP").others.map((r) => r.name)).toEqual(["Alpha"]);
  });
});

describe("AnalyticsScopeSelector", () => {
  it("labels the whole platform when nothing is selected", () => {
    render(<AnalyticsScopeSelector value={[]} onChange={vi.fn()} />);
    expect(trigger().textContent).toContain("rework.analytics.scope.platform");
  });

  it("labels one team by name and several by count", () => {
    render(<AnalyticsScopeSelector value={["t-b"]} onChange={vi.fn()} />);
    expect(trigger().textContent).toContain("Beta");
    act(() => root!.render(<AnalyticsScopeSelector value={["t-b", "t-c"]} onChange={vi.fn()} />));
    expect(trigger().textContent).toContain("rework.analytics.scope.teamsSelected:2");
  });

  it("lists every team with its member count, small teams included", () => {
    render(<AnalyticsScopeSelector value={[]} onChange={vi.fn()} />);
    act(() => trigger().click());
    const rows = rowNames();
    expect(rows[0]).toContain("rework.analytics.scope.platform");
    expect(rows).toContainEqual(expect.stringContaining("Gamma"));
    expect(rows.find((r) => r.includes("Gamma"))).toContain("rework.analytics.scope.members:1");
  });

  it("lists the applied teams first", () => {
    render(<AnalyticsScopeSelector value={["t-f"]} onChange={vi.fn()} />);
    act(() => trigger().click());
    expect(rowNames()[1]).toContain("Zeta");
    expect(container.textContent).toContain("rework.analytics.scope.selected");
  });

  it("applies the draft in catalog order and closes", () => {
    const onChange = vi.fn();
    render(<AnalyticsScopeSelector value={[]} onChange={onChange} />);
    act(() => trigger().click());
    tick("Delta");
    tick("Alpha");
    act(() => button("rework.analytics.scope.apply").click());
    expect(onChange).toHaveBeenCalledWith(["t-a", "t-d"]);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("discards the draft on cancel", () => {
    const onChange = vi.fn();
    render(<AnalyticsScopeSelector value={["t-a"]} onChange={onChange} />);
    act(() => trigger().click());
    tick("Beta");
    act(() => button("rework.analytics.scope.cancel").click());
    expect(onChange).not.toHaveBeenCalled();
    act(() => trigger().click());
    const beta = [...container.querySelectorAll('[role="dialog"] label')].find((el) =>
      el.textContent?.includes("Beta"),
    )!;
    expect(beta.querySelector("input")!.checked).toBe(false);
  });

  it("clears the selection when the whole platform is ticked", () => {
    const onChange = vi.fn();
    render(<AnalyticsScopeSelector value={["t-a", "t-b"]} onChange={onChange} />);
    act(() => trigger().click());
    tick("rework.analytics.scope.platform");
    act(() => button("rework.analytics.scope.apply").click());
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

const RANGE = { since: "2026-10-01T00:00:00.000Z", until: "2026-10-27T00:00:00.000Z" };

describe("AnalyticsScopeSummary", () => {
  it("renders nothing for the whole platform", () => {
    render(<AnalyticsScopeSummary value={[]} timeRange={RANGE} />);
    expect(container.textContent).toBe("");
  });

  it("shows four chips, how many more and the distinct member total", () => {
    render(<AnalyticsScopeSummary value={h.rows.map((r) => r.team_id)} timeRange={RANGE} />);
    const text = container.textContent ?? "";
    expect(text).toContain("Alpha");
    expect(text).toContain("Delta");
    expect(text).not.toContain("Epsilon");
    expect(text).toContain("rework.analytics.scope.more:2");
    // 20 distinct people, not the 27 of the per-team sum.
    expect(text).toContain("rework.analytics.scope.membersTotal:20");
  });

  it("omits the member total while it is unknown", () => {
    h.adoption.mockReturnValueOnce({ data: { people_with_access: null } });
    render(<AnalyticsScopeSummary value={["t-a"]} timeRange={RANGE} />);
    expect(container.textContent).not.toContain("membersTotal");
  });
});

describe("AnalyticsScopeSelector before the catalog loads", () => {
  it("cannot apply, so a selection is never cleared by an empty catalog", () => {
    h.catalog.mockReturnValue({ data: undefined });
    render(<AnalyticsScopeSelector value={["t-a"]} onChange={vi.fn()} />);
    act(() => trigger().click());
    expect(button("rework.analytics.scope.apply").disabled).toBe(true);
  });
});
