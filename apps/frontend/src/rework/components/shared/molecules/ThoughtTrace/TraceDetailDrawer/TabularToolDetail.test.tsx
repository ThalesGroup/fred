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
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TabularToolDetail } from "./TabularToolDetail";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <article>{text}</article>,
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

it("toggles between the first 20 catalog lines and the full catalog above the tables", () => {
  const markdown = Array.from({ length: 25 }, (_, index) => `line-${String(index + 1).padStart(2, "0")}`).join("\n");
  act(() =>
    root.render(
      <TabularToolDetail
        data={{
          kind: "descriptions",
          documents: [
            {
              document_uid: "book",
              document_name: "Budget.xlsx",
              kind: "spreadsheet",
              markdown,
              tables: [{ query_alias: "revenue", columns: [{ name: "amount", dtype: "float" }] }],
            },
          ],
        }}
      />,
    ),
  );

  const catalog = container.querySelector("article");
  const button = container.querySelector("button");
  const tableHeading = container.querySelector("h4");
  expect(catalog?.textContent).toContain("line-20");
  expect(catalog?.textContent).not.toContain("line-21");
  expect(button?.textContent).toContain("showFullCatalog");
  expect(tableHeading?.textContent).toContain("tablesHeading");
  expect(catalog?.compareDocumentPosition(tableHeading!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

  act(() => button?.click());
  expect(catalog?.textContent).toContain("line-25");
  expect(button?.textContent).toContain("showCatalogPreview");

  act(() => button?.click());
  expect(catalog?.textContent).not.toContain("line-21");
});

it("expands category values and integer and float bounds from a right-side control", () => {
  act(() =>
    root.render(
      <TabularToolDetail
        data={{
          kind: "descriptions",
          documents: [
            {
              document_uid: "book",
              document_name: "Fleet.xlsx",
              kind: "spreadsheet",
              markdown: "# Fleet",
              tables: [
                {
                  query_alias: "fleet",
                  columns: [
                    {
                      name: "Statut",
                      dtype: "string",
                      is_categorical: true,
                      has_two_values: true,
                      sample_values: ["nok", "ok"],
                    },
                    { name: "Km_2023", dtype: "integer", min_value: 0, max_value: 250 },
                    { name: "Km_2024", dtype: "float", min_value: -1.5, max_value: 2.25 },
                    { name: "Km_2025", dtype: "integer" },
                  ],
                },
              ],
            },
          ],
        }}
      />,
    ),
  );

  const statusName = [...container.querySelectorAll("span")].find((element) => element.textContent === "Statut");
  const disclosure = statusName?.closest("details");
  expect(disclosure?.open).toBe(false);
  expect(disclosure?.querySelector("summary code")?.textContent).toBe("rework.chatTrace.tabular.categorical");
  expect(disclosure?.querySelector(":scope > code")?.textContent).toBe("nok / ok");
  act(() => disclosure?.querySelector("summary")?.click());
  expect(disclosure?.open).toBe(true);
  expect(container.textContent).not.toContain("twoValues");

  const distanceName = [...container.querySelectorAll("span")].find((element) => element.textContent === "Km_2023");
  const distanceDisclosure = distanceName?.closest("details");
  expect(distanceDisclosure?.open).toBe(false);
  expect(distanceDisclosure?.querySelector("summary code")?.textContent).toBe("integer");
  act(() => distanceDisclosure?.querySelector("summary")?.click());
  expect(distanceDisclosure?.open).toBe(true);
  expect(distanceDisclosure?.querySelector(":scope > code")?.textContent).toBe("min 0 · max 250");
  const floatName = [...container.querySelectorAll("span")].find((element) => element.textContent === "Km_2024");
  expect(floatName?.closest("details")?.querySelector(":scope > code")?.textContent).toBe("min -1.5 · max 2.25");
  const oldDistanceName = [...container.querySelectorAll("span")].find((element) => element.textContent === "Km_2025");
  expect(oldDistanceName?.closest("details")?.querySelector(":scope > code")?.textContent).toBe("min — · max —");
});
