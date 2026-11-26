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

// The card registers its file on every mount (that lights the launcher).
// Loading history never opens the pane; the Preview button does.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SpreadsheetPreviewPartData } from "./types";

const state = vi.hoisted(() => ({
  session: "s-1",
  now: 1_000_000,
  dispatched: [] as { type: string }[],
  latest: {} as Record<string, number>,
}));

vi.mock("react-redux", () => ({
  useDispatch: () => (action: { type: string }) => state.dispatched.push(action),
  useSelector: (select: (root: unknown) => unknown) => select({ spreadsheetPreview: { latest: state.latest } }),
}));
vi.mock("../useOpenSessionId", () => ({ useMountSessionId: () => state.session }));
vi.mock("./SpreadsheetDownloadButton", () => ({
  default: ({ href, fileName }: { href: string; fileName: string }) => (
    <a href={href} download={fileName}>
      download
    </a>
  ),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { version?: number }) => (options?.version ? `${key}:${options.version}` : key),
  }),
}));

// History can first arrive long after this module loads. Its age is not a live signal.
const clock = vi.spyOn(Date, "now").mockImplementation(() => state.now);
afterAll(() => clock.mockRestore());
const { SpreadsheetCardRenderer } = await import("./SpreadsheetCardRenderer");
const { UiParts } = await import("../../../components/shared/molecules/UiParts/UiParts");
const { openSpreadsheet, registerSpreadsheet } = await import("./spreadsheetPreviewSlice");
const { requestSidePanelOpen } = await import("../sidePanelOpenRequestSlice");
const REGISTER = registerSpreadsheet.type;
const OPEN = [openSpreadsheet.type, requestSidePanelOpen.type];
const PAGE_LOADED_AT = state.now;

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

const part = (id: string): SpreadsheetPreviewPartData => ({
  type: "spreadsheet_preview",
  preview_id: id,
  document_id: id,
  content_id: `content-${id}`,
  file_name: `${id}.xlsx`,
  xlsx_download_url: `/control-plane/v1/spaces/t/sessions/s-1/files/${id}/content`,
  preview_url: `/control-plane/v1/spaces/t/sessions/s-1/files/${id}/preview`,
});

async function mount(id: string, extra: Partial<SpreadsheetPreviewPartData> = {}) {
  await act(async () => root.render(<SpreadsheetCardRenderer part={{ ...part(id), ...extra } as never} />));
}

const types = () => state.dispatched.map((action) => action.type);

beforeEach(() => {
  state.dispatched = [];
  state.session = "s-1";
  state.latest = {};
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("SpreadsheetCardRenderer", () => {
  it("renders each file from one message through UiParts, retaining downloads and workbook badges", async () => {
    state.now = PAGE_LOADED_AT + 1000;
    state.latest = { same: 2 };
    const v1 = { ...part("same-v1"), workbook_id: "same", version: 1 };
    const v2 = { ...part("same-v2"), workbook_id: "same", version: 2 };
    await act(async () => root.render(<UiParts parts={[v1, v2, { ...v2 }]} />));

    const cards = [...container.querySelectorAll('[role="note"]')];
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain("capability.spreadsheet.card.version:1");
    expect(cards[1].textContent).toContain("capability.spreadsheet.card.latest");
    expect([...container.querySelectorAll("a")].map((a) => [a.getAttribute("href"), a.download])).toEqual([
      [v1.xlsx_download_url, v1.file_name],
      [v2.xlsx_download_url, v2.file_name],
    ]);
    state.dispatched = [];
    await act(async () => cards[0].querySelector("button")!.click());
    expect(state.dispatched).toContainEqual(openSpreadsheet({ sessionId: "s-1", preview: v1 }));
  });

  it.each([1000, 60_000])("registers history loaded %i ms later without opening the pane", async (delay) => {
    state.now = PAGE_LOADED_AT + delay;
    await mount(`replayed-${delay}`);
    expect(types()).toEqual([REGISTER]);
    expect(container.textContent).toContain(`replayed-${delay}.xlsx`);

    state.dispatched = [];
    await act(async () => root.unmount());
    root = createRoot(container);
    await mount(`replayed-${delay}`);
    expect(types()).toEqual([REGISTER]);
  });

  it("registers nothing once the user left the conversation", async () => {
    state.session = "";
    await mount("elsewhere");
    expect(state.dispatched).toEqual([]);
  });

  it("opens the pane from the preview button", async () => {
    state.now = PAGE_LOADED_AT + 1000;
    await mount("button");
    state.dispatched = [];
    const open = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("card.open"))!;
    await act(async () => open.click());
    expect(types()).toEqual(OPEN);
  });

  it("marks the latest version of a workbook and keeps older cards usable", async () => {
    state.now = PAGE_LOADED_AT + 1000;
    state.latest = { w1: 2 };
    await mount("v2", { workbook_id: "w1", version: 2 });
    expect(container.textContent).toContain("capability.spreadsheet.card.latest");

    await act(async () => root.unmount());
    root = createRoot(container);
    await mount("v1", { workbook_id: "w1", version: 1 });
    expect(container.textContent).toContain("capability.spreadsheet.card.version:1");
    expect(container.textContent).toContain("download");

    // A live v3 moves the marker: the v1 card now reads "Version 1" still, v3 is latest.
    state.latest = { w1: 3 };
    await act(async () => root.unmount());
    root = createRoot(container);
    await mount("v3", { workbook_id: "w1", version: 3 });
    expect(container.textContent).toContain("capability.spreadsheet.card.latest");
  });

  it("shows no version marker for a single-version workbook", async () => {
    state.now = PAGE_LOADED_AT + 1000;
    state.latest = { w1: 1 };
    await mount("only", { workbook_id: "w1", version: 1 });
    expect(container.textContent).not.toContain("card.latest");
    expect(container.textContent).not.toContain("card.version");
  });
});
