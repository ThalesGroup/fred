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

// Two capabilities deliver this card, and an agent may have only one of them:
// "Open preview" must ask for the pane of the capability that produced the deck,
// or the page finds no such panel and nothing opens. An agent that regenerates a
// deck within one answer shows one card for it, the last.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PptPreviewPartData } from "./types";

const dispatched = vi.hoisted(() => [] as { type: string; payload: unknown }[]);

vi.mock("react-redux", () => ({
  useDispatch: () => (action: { type: string; payload: unknown }) => dispatched.push(action),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../useOpenSessionId", () => ({ useMountSessionId: () => "s1" }));
vi.mock("./PptxDownloadButton", () => ({ default: () => null }));

const { PptPreviewCardRenderer } = await import("./PptPreviewCardRenderer");
const { requestSidePanelOpen } = await import("../sidePanelOpenRequestSlice");

const deck: PptPreviewPartData = {
  type: "ppt_preview",
  preview_id: "deck-1",
  title: "Q3 review",
  pdf_download_url: "/fs/download/deck-1.pdf",
  version: "v1",
};

let root: Root | null = null;

function mount(part: PptPreviewPartData, messageParts?: PptPreviewPartData[]): HTMLElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<PptPreviewCardRenderer part={part as never} messageParts={messageParts as never} />));
  return container;
}

function clickOpen(part: PptPreviewPartData) {
  const container = mount(part);
  const button = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("capability.ppt_filler.preview.open"),
  );
  act(() => button!.click());
  return dispatched.filter((a) => a.type === requestSidePanelOpen.type).map((a) => a.payload);
}

afterEach(() => {
  act(() => root?.unmount());
  root = null;
  dispatched.length = 0;
  document.body.innerHTML = "";
});

describe("PptPreviewCardRenderer", () => {
  it("opens the pane of the capability that produced the deck", () => {
    expect(clickOpen({ ...deck, capability_id: "ppt_builder" })).toEqual([
      { capabilityId: "ppt_builder", widget: "ppt_preview_pane" },
    ]);
  });

  it("opens the ppt_filler pane for a part that predates the field", () => {
    expect(clickOpen(deck)).toEqual([{ capabilityId: "ppt_filler", widget: "ppt_preview_pane" }]);
  });

  it("shows only the last card of a deck regenerated in the same message", () => {
    const first = deck;
    const second = { ...deck, version: "v2" };
    const unrelated = { ...deck, preview_id: "deck-2" };
    const parts = [first, unrelated, second];

    expect(mount(first, parts).textContent).toBe("");
    expect(mount(unrelated, parts).textContent).toContain("Q3 review");
    expect(mount(second, parts).textContent).toContain("Q3 review");
  });
});
