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
