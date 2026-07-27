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
import SizeByTypeBar from "./SizeByTypeBar.tsx";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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

const segments = [
  { key: "pdf", label: "PDF", value: 100, color: "#f97316" },
  { key: "text", label: "Texte", value: 0, color: "#4e8cff" },
  { key: "ppt", label: "PPT", value: 200, color: "#f43f5e" },
  { key: "excel", label: "Excel", value: 0, color: "#22c55e" },
  { key: "other", label: "Autres", value: 0, color: "#64748b" },
];

describe("SizeByTypeBar", () => {
  it("only lists non-zero segments in the legend", () => {
    render(<SizeByTypeBar title="Size" segments={segments} isLoading={false} isError={false} formatValue={String} />);
    const items = Array.from(container.querySelectorAll("li")).map((li) => li.textContent);
    expect(items).toEqual(["PDF", "PPT"]);
  });

  it("shows the empty state when every segment is zero", () => {
    render(
      <SizeByTypeBar
        title="Size"
        segments={segments.map((s) => ({ ...s, value: 0 }))}
        isLoading={false}
        isError={false}
        emptyMessage="Nothing yet"
        formatValue={String}
      />,
    );
    expect(container.textContent).toContain("Nothing yet");
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });

  it("shows the error state", () => {
    render(<SizeByTypeBar title="Size" segments={[]} isLoading={false} isError formatValue={String} />);
    expect(container.textContent).toContain("common.loadingError");
  });
});
