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

// pdf.js worker budget across regenerations (mirrors ppt_filler's test). Each port
// serves exactly one load, so: one worker per loaded document, none while a fetch
// is in flight, and every one terminated.

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

vi.mock("./usePptxPreview", () => ({
  usePptxPreview: () => ({
    objectUrl: preview.url,
    isLoading: preview.url === null,
    error: null,
    refetch: () => undefined,
  }),
}));

const deck = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("./useSessionPptxPreview", () => ({ useSessionPptxPreview: () => deck.current }));

const { PptxPreviewPane } = await import("./PptxPreviewPane");

let container: HTMLDivElement;
let root: Root;

const render = () =>
  act(() => {
    root.render(<PptxPreviewPane capabilityId="pptx_generator" onClose={() => undefined} />);
  });

/** One generation: the fetch is in flight, then its blob lands. */
function fill(version: string, url: string) {
  deck.current = {
    type: "pptx_generated",
    preview_id: "p1",
    title: "d",
    pdf_download_url: "/d",
    version,
    pptx_download_url: null,
    file_name: null,
  };
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

describe("PptxPreviewPane pdf.js worker budget", () => {
  it("spawns nothing while there is no deck to render", () => {
    render();
    expect(workers.created).toHaveLength(0);
  });

  it("spawns nothing while a generation is still fetching", () => {
    deck.current = {
      type: "pptx_generated",
      preview_id: "p1",
      title: "d",
      pdf_download_url: "/d",
      version: "v1",
      pptx_download_url: null,
      file_name: null,
    };
    render();

    expect(workers.created).toHaveLength(0);
  });

  it("spawns exactly one worker per rendered document, ten regenerations deep", () => {
    for (let i = 1; i <= 10; i++) fill(`v${i}`, `blob:${i}`);

    expect(workers.created).toHaveLength(10);
  });

  it("leaves at most one worker alive: every superseded one is terminated", () => {
    for (let i = 1; i <= 10; i++) fill(`v${i}`, `blob:${i}`);

    expect(workers.created.filter((w) => !w.terminated)).toHaveLength(1);
  });
});
