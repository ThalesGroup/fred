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
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import KpiStatCard from "./KpiStatCard";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it("renders caller-owned state labels without a translation provider", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    for (const state of ["loading", "error", "unavailable"] as const) {
      act(() =>
        root.render(
          <KpiStatCard
            label="Runs"
            isLoading={state === "loading"}
            isError={state === "error"}
            unavailable={state === "unavailable"}
            loadingLabel="Fetching"
            errorLabel="Failed"
            noDataLabel="Unavailable"
          />,
        ),
      );
      expect(container.textContent).toBe(
        `Runs${{ loading: "Fetching", error: "Failed", unavailable: "Unavailable" }[state]}`,
      );
    }
  } finally {
    act(() => root.unmount());
  }
});

it("retains neutral styling by default and accepts outcome tones", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    act(() => root.render(<KpiStatCard label="Passed" value={4} isLoading={false} isError={false} />));
    expect(container.querySelector("section")?.dataset.tone).toBe("neutral");
    act(() => root.render(<KpiStatCard label="Passed" value={4} tone="success" isLoading={false} isError={false} />));
    expect(container.querySelector("section")?.dataset.tone).toBe("success");
    expect(container.textContent).toBe("Passed4");
  } finally {
    act(() => root.unmount());
  }
});

it("shows an optional hint as a focusable info bubble in the corner", () => {
  const html = renderToStaticMarkup(
    <KpiStatCard label="Searches" hint="Billed by the provider" value={2} isLoading={false} isError={false} />,
  );
  expect(html).toContain('aria-label="Billed by the provider"');
  expect(html).toContain(">info<");
  expect(
    renderToStaticMarkup(<KpiStatCard label="Searches" value={2} isLoading={false} isError={false} />),
  ).not.toContain("info");
});

it("shows a fixed number of decimals when asked, without rounding to the locale default", () => {
  const html = renderToStaticMarkup(
    <KpiStatCard label="Cost" value={0.005} fractionDigits={4} isLoading={false} isError={false} />,
  );
  expect(html).toContain((0.005).toLocaleString(undefined, { minimumFractionDigits: 4 }));
});

it("shows the caption under the value, including a zero value, and hides it while loading", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    act(() => root.render(<KpiStatCard label="Tokens" value={0} caption="0 runs" isLoading={false} isError={false} />));
    expect(container.textContent).toBe("Tokens00 runs");
    act(() => root.render(<KpiStatCard label="Tokens" caption="0 runs" isLoading isError={false} />));
    expect(container.textContent).toBe("TokensLoading");
  } finally {
    act(() => root.unmount());
  }
});

it("shows a preformatted value and change with the tone the caller picks", () => {
  const html = renderToStaticMarkup(
    <KpiStatCard
      label="Failed answers"
      value={0.018}
      displayValue="1.8%"
      deltaLabel="-0.6 pts"
      deltaTone="positive"
      isLoading={false}
      isError={false}
    />,
  );
  expect(html).toContain("1.8%");
  expect(html).toMatch(/class="[^"]*deltaPositive[^"]*">-0.6 pts</);
});

it("puts the change on its own line with a direction glyph that reads without colour", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    act(() =>
      root.render(
        <KpiStatCard
          label="Failed answers"
          value={0.018}
          displayValue="1.8%"
          deltaLabel="-0.6 pts"
          deltaTone="positive"
          deltaDirection="down"
          isLoading={false}
          isError={false}
        />,
      ),
    );
    const value = [...container.querySelectorAll("span")].find((el) => el.textContent === "1.8%")!;
    expect(value.nextElementSibling?.textContent).toBe("▼ -0.6 pts");
    expect(value.nextElementSibling?.querySelector('[aria-hidden="true"]')?.textContent).toBe("▼ ");
    act(() => root.render(<KpiStatCard label="Runs" value={4} delta={2} isLoading={false} isError={false} />));
    expect(container.textContent).toBe("Runs4▲ +2");
  } finally {
    act(() => root.unmount());
  }
});

it("sizes the value as asked, medium by default", () => {
  const html = (size?: "medium" | "large") =>
    renderToStaticMarkup(<KpiStatCard label="Users" value={3} size={size} isLoading={false} isError={false} />);
  expect(html()).toContain('data-size="medium"');
  expect(html("large")).toContain('data-size="large"');
});
