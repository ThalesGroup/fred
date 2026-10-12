// @vitest-environment jsdom
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
import { parseDocumentTreeTrace } from "../../../../../utils/documentTreeTrace";
import { DocumentTreeDetail } from "./DocumentTreeDetail";
import en from "../../../../../../locales/en/translation.json";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { language: "en" },
    t: (key: string, options: Record<string, unknown> = {}) => {
      const fields = en.rework.chatTrace.documentTree as Record<string, string>;
      const field = key.substring(key.lastIndexOf(".") + 1);
      let value =
        fields[options.count === undefined ? field : field + (options.count === 1 ? "_one" : "_other")] ?? key;
      for (const [name, replacement] of Object.entries(options))
        value = value.replace(`{{${name}}}`, String(replacement));
      return value;
    },
  }),
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
function render(text: string) {
  const data = parseDocumentTreeTrace(text)!;
  act(() => root.render(<DocumentTreeDetail data={data} />));
}
function leaf(uid: string, name: string, added: string | null, extra: Record<string, unknown> = {}) {
  return JSON.stringify({ uid, name, added_to_kb: added, created: null, modified: null, ...extra });
}

it("shows compact rows and expands only one document without exposing ids", () => {
  render(
    "Docs [folder:hidden-folder]/\n  " +
      leaf("hidden-a", "Report.pdf", "2026-10-12T09:00:00Z", {
        title: "Platform design",
        file_type: "pdf",
        language: "fr",
        page_count: 24,
        labels: ["Architecture"],
        source: "webdav",
      }) +
      "\n  " +
      leaf("hidden-b", "Older.pdf", "2026-10-12T08:00:00Z"),
  );
  expect(container.textContent).toContain("2 documents displayed");
  expect(container.textContent).toContain("Report.pdf");
  expect(container.textContent).toContain("Most recent displayed");
  expect(container.textContent).not.toContain("Platform design");
  expect(container.textContent).not.toContain("hidden-");
  const summaries = container.querySelectorAll("details details > summary");
  act(() => (summaries[0] as HTMLElement).click());
  expect(container.textContent).toContain("Platform design");
  expect(container.textContent).toContain("2026-10-12 09:00:00Z");
  expect(container.textContent).toContain("24 pages");
  expect(container.textContent).toContain("Architecture");
  act(() => (summaries[1] as HTMLElement).click());
  expect(container.querySelectorAll("dl")).toHaveLength(1);
  expect(container.textContent).not.toContain("Platform design");
  expect(container.textContent).not.toContain("hidden-");
});

it("shows incompleteness and unknown dates, omits absent optional metadata, and renders labels as text", () => {
  render(
    "Listing incomplete: omitted documents may be more recent.\nDocs/\n  " +
      leaf("private", "Report.pdf", null, { labels: ["<script>alert(1)</script>"], page_count: 0 }),
  );
  expect(container.textContent).toContain("Partial listing");
  expect(container.textContent).toContain("Added to Fred: Unknown");
  expect(container.textContent).not.toContain("Most recent displayed");
  act(() => (container.querySelector("details details > summary") as HTMLElement).click());
  expect(container.textContent).toContain("0 pages");
  expect(container.textContent).toContain("<script>alert(1)</script>");
  expect(container.querySelector("script")).toBeNull();
  expect(container.textContent).not.toContain("MIME type");
});

it("keeps historical dates distinct from Fred arrival", () => {
  render("Docs/\n  Old.pdf [private-id] (uploaded 2026-01-01)");
  expect(container.textContent).toContain("Historical upload date: 2026-01-01");
  expect(container.textContent).not.toContain("Most recent displayed");
  expect(container.textContent).not.toContain("private-id");
});
