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

// The pane's pdf.js worker budget, iteration after iteration.
//
// Each worker is a real thread loading the pdf.js bundle, and each PORT may serve
// exactly one load - pdf.js caches a PDFWorker per port and throws
// "the worker is being destroyed" on the second. So the invariant is narrow:
// ONE worker per document actually loaded, none while a fetch is in flight, and
// every one of them terminated. This test counts them across a re-fill loop,
// which is what a user correcting a deck does over and over.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const workers = vi.hoisted(() => ({ created: [] as { terminated: boolean }[] }));

class FakeWorker {
  terminated = false;
  constructor() {
    workers.created.push(this);
  }
  terminate() {
    this.terminated = true;
  }
}
vi.stubGlobal("Worker", FakeWorker);

const preview = vi.hoisted(() => ({ url: null as string | null }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? "" }),
}));
vi.mock("@shared/atoms/Icon/Icon", () => ({ default: () => null }));
vi.mock("@shared/atoms/IconButton/IconButton", () => ({ default: () => null }));
vi.mock("./PptxDownloadButton", () => ({ default: () => null }));
vi.mock("react-pdf/dist/Page/AnnotationLayer.css", () => ({}));

// react-pdf is the consumer of the port; the counts are what matter here.
vi.mock("react-pdf", () => ({
  Document: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: { workerPort: null as unknown, workerSrc: "" } },
}));

vi.mock("./usePptPreview", () => ({
  usePptPreview: () => ({
    objectUrl: preview.url,
    isLoading: preview.url === null,
    error: null,
    refetch: () => undefined,
  }),
}));

const deck = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("./useSessionPptPreview", () => ({ useSessionPptPreview: () => deck.current }));

const { PptPreviewPane } = await import("./PptPreviewPane");

let container: HTMLDivElement;
let root: Root;

const render = () =>
  act(() => {
    root.render(<PptPreviewPane capabilityId="ppt_filler" onClose={() => undefined} />);
  });

/** One fill: the fetch is in flight, then its blob lands. */
function fill(version: string, url: string) {
  deck.current = { type: "ppt_preview", preview_id: "p1", title: "d", pdf_download_url: "/d", version };
  preview.url = null;
  render();
  preview.url = url;
  render();
}

beforeEach(() => {
  workers.created = [];
  preview.url = null;
  deck.current = null;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PptPreviewPane pdf.js worker budget", () => {
  it("spawns nothing while there is no deck to render", () => {
    render();
    expect(workers.created).toHaveLength(0);
  });

  it("spawns nothing while a fill is still fetching", () => {
    deck.current = { type: "ppt_preview", preview_id: "p1", title: "d", pdf_download_url: "/d", version: "v1" };
    render();

    expect(workers.created).toHaveLength(0);
  });

  it("spawns exactly one worker per rendered document, ten re-fills deep", () => {
    for (let i = 1; i <= 10; i++) fill(`v${i}`, `blob:${i}`);

    expect(workers.created).toHaveLength(10);
  });

  it("leaves at most one worker alive: every superseded one is terminated", () => {
    for (let i = 1; i <= 10; i++) fill(`v${i}`, `blob:${i}`);

    expect(workers.created.filter((w) => !w.terminated)).toHaveLength(1);
  });
});
