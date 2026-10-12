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

vi.mock("../../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ siteDisplayName: "Atlas" }),
}));

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

function showMetadata(index = 0) {
  const button = container.querySelectorAll("button")[index];
  act(() => button.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
  return document.querySelector('[role="tooltip"]')!;
}

it("shows nested filesystem rows without dates and reveals metadata on the info action", () => {
  render(
    "Docs/\n  Architecture/\n    " +
      leaf("hidden-a", "Report.pdf", "2026-10-12T09:00:00Z", {
        title: "Platform design",
        file_type: "pdf",
        language: "fr",
        page_count: 24,
        labels: ["Architecture"],
        source: "webdav",
      }) +
      "\n    " +
      leaf("hidden-b", "Older.pdf", "2026-10-12T08:00:00Z"),
  );
  expect(container.textContent).toContain("2 documents displayed");
  expect(container.textContent).not.toContain("2026-");
  expect(container.textContent).not.toContain("Added to");
  expect(container.textContent).not.toContain("Platform design");
  expect(container.textContent).not.toContain("Most recent displayed");
  expect(container.textContent).not.toContain("hidden-");
  expect(container.querySelector("details details summary")?.textContent).toContain("Architecture");
  expect(container.querySelectorAll("button")).toHaveLength(2);
  const panel = showMetadata();
  expect(panel.textContent).toContain("Platform design");
  expect(panel.textContent).toContain("2026-10-12 09:00:00 UTC");
  expect(panel.textContent).toContain("24 pages");
  expect(panel.textContent).toContain("Most recent displayed");
  expect(panel.textContent).not.toContain("hidden-");
  expect(panel.textContent).not.toContain("File creation");
  expect(panel.textContent).not.toContain("Modification");
  expect(Array.from(panel.querySelectorAll("dt"), (n) => n.textContent)).not.toContain("Format");
  expect(container.querySelector("dl")).toBeNull();
});

it("places a discreet truncation marker at the end and keeps missing optional fields out of metadata", () => {
  render(
    "Listing incomplete: omitted documents may be more recent.\nDocs/\n  " +
      leaf("private", "Report.pdf", null, { labels: ["<script>alert(1)</script>"], page_count: 0 }),
  );
  expect(container.firstElementChild?.lastElementChild?.textContent).toBe("Truncated");
  expect(container.textContent).not.toContain("Partial listing");
  expect(container.textContent).not.toContain("Unknown");
  const panel = showMetadata();
  expect(panel.querySelector("dt")?.textContent).toBe("Added to Atlas");
  expect(panel.textContent).toContain("Unknown");
  expect(panel.textContent).toContain("0 pages");
  expect(panel.textContent).toContain("<script>alert(1)</script>");
  expect(panel.querySelector("script")).toBeNull();
  expect(panel.textContent).not.toContain("MIME type");
});

it("keeps historical dates distinct from arrival in the knowledge base", () => {
  render("Docs/\n  Old.pdf [private-id] (uploaded 2026-01-01)");
  expect(container.textContent).not.toContain("2026-01-01");
  const panel = showMetadata();
  expect(panel.textContent).toContain("Historical upload date");
  expect(panel.textContent).toContain("2026-01-01");
  expect(panel.textContent).not.toContain("Most recent displayed");
  expect(panel.textContent).not.toContain("private-id");
});

it("opens metadata through keyboard focus and dismisses it with Escape", () => {
  render("Docs/\n  " + leaf("private", "Report.pdf", null));
  const button = container.querySelector("button")!;
  act(() => {
    button.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    button.focus();
  });
  expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
  act(() => button.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(document.querySelector('[role="tooltip"]')).toBeNull();
});

it("retains empty leaf folders without inventing file rows", () => {
  render("Docs/\n  Empty/");
  expect(container.querySelectorAll("details")).toHaveLength(2);
  expect(container.textContent).toContain("Empty");
  expect(container.querySelectorAll("button")).toHaveLength(0);
  expect(container.textContent).not.toContain("Truncated");
});
