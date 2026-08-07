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

// Coverage for #2273: a large PDF used to mount one live <canvas> per page the
// moment the document loaded, which allocated gigabytes and killed the browser
// tab. These tests pin the three guarantees that replaced it — a bounded set of
// mounted pages, on-demand byte-range fetching, and an opt-in wall in front of
// a pathological page count.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../security/AuthContext", () => ({
  useAuthToken: () => "test-token",
}));

// Captures the props react-pdf's <Document> was called with, so a test can both
// assert on them (options) and drive the load lifecycle (onLoadSuccess).
const documentProps = vi.hoisted(() => ({ current: null as any }));
vi.mock("react-pdf", () => ({
  Document: (props: any) => {
    documentProps.current = props;
    return <div data-testid="pdf-document">{props.children}</div>;
  },
  Page: ({ pageNumber }: any) => <canvas data-testid="pdf-page" data-page={pageNumber} />,
  pdfjs: { GlobalWorkerOptions: {} },
}));

// Lets a test play the role of the browser's scroll: hand the component's own
// IntersectionObserver callback a batch of entries for chosen page slots.
const io = vi.hoisted(() => ({ callback: null as any, observed: [] as Element[] }));

class MockIntersectionObserver {
  constructor(callback: any) {
    io.callback = callback;
  }
  observe(element: Element) {
    io.observed.push(element);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);
vi.stubGlobal(
  "Worker",
  class {
    terminate() {}
  },
);

import { PdfStreamingDocumentViewer, reduceMountedPages } from "./PdfStreamingDocumentViewer.tsx";

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

/** Drive react-pdf's load callback with a document of `numPages` pages. The
 * geometry probe (`getPage(1)`) is async, so flush microtasks too. */
async function loadDocument(numPages: number) {
  await act(async () => {
    documentProps.current.onLoadSuccess({
      numPages,
      getPage: () => Promise.resolve({ getViewport: () => ({ width: 210, height: 297 }) }),
    });
    await Promise.resolve();
  });
}

/** Feed the component's IntersectionObserver a batch of entries, addressing
 * page slots by their `data-page-number`. */
function scrollTo(entries: { page: number; visible: boolean }[]) {
  act(() => {
    io.callback(
      entries.map(({ page, visible }) => ({
        target: io.observed.find((el) => (el as HTMLElement).dataset.pageNumber === String(page)),
        isIntersecting: visible,
      })),
    );
  });
}

const mountedPageNumbers = () =>
  Array.from(container.querySelectorAll("[data-testid='pdf-page']")).map((el) =>
    Number((el as HTMLElement).dataset.page),
  );

beforeEach(() => {
  documentProps.current = null;
  io.callback = null;
  io.observed = [];
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("PdfStreamingDocumentViewer page virtualization (#2273)", () => {
  it("reserves a slot for every page but mounts only the pages in view", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(200);

    // The scrollbar must still reflect the real document length…
    expect(container.querySelectorAll("[data-page-number]")).toHaveLength(200);
    // …but nothing beyond the initial page is a live canvas.
    expect(mountedPageNumbers()).toEqual([1]);
  });

  it("mounts pages as they scroll into the band and unmounts them on the way out", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(200);

    scrollTo([
      { page: 1, visible: false },
      { page: 40, visible: true },
      { page: 41, visible: true },
    ]);
    expect(mountedPageNumbers()).toEqual([40, 41]);

    scrollTo([
      { page: 40, visible: false },
      { page: 41, visible: false },
      { page: 80, visible: true },
    ]);
    expect(mountedPageNumbers()).toEqual([80]);
  });

  it("observes every page slot so no page is stranded as a permanent placeholder", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(120);

    expect(io.observed).toHaveLength(120);
  });
});

describe("PdfStreamingDocumentViewer transport options (#2273)", () => {
  // `disableStream` must be true, not just `disableAutoFetch`: pdf.js cancels its
  // initial full-file request in favour of range requests only when streaming is
  // off. Left at false, a 50 MB PDF downloaded whole (one 200 of 51.86 MB) on top
  // of its range requests, defeating the point of virtualizing the pages.
  it("asks pdf.js to fetch byte ranges on demand instead of the whole file", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(10);

    expect(documentProps.current.options).toMatchObject({ disableAutoFetch: true, disableStream: true });
  });

  it("keeps the options object identity stable so react-pdf never reloads the document", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    const first = documentProps.current.options;
    await loadDocument(10);
    scrollTo([{ page: 2, visible: true }]);

    expect(documentProps.current.options).toBe(first);
  });
});

describe("PdfStreamingDocumentViewer large-document guard (#2273)", () => {
  it("renders no page at all until the user opts in, past the page-count ceiling", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(900);

    expect(mountedPageNumbers()).toEqual([]);
    expect(container.querySelectorAll("[data-page-number]")).toHaveLength(0);
    expect(container.textContent).toContain("rework.resources.preview.pdf.largeTitle");
  });

  it("renders the (still virtualized) document once the user confirms", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(900);

    act(() => {
      container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(container.querySelectorAll("[data-page-number]")).toHaveLength(900);
    expect(mountedPageNumbers()).toEqual([1]);
  });

  it("renders a document under the ceiling with no guard", async () => {
    render(<PdfStreamingDocumentViewer documentUid="doc-1" />);
    await loadDocument(499);

    expect(container.textContent).not.toContain("rework.resources.preview.pdf.largeTitle");
    expect(container.querySelectorAll("[data-page-number]")).toHaveLength(499);
  });
});

describe("reduceMountedPages", () => {
  it("returns the same set instance when a batch changes nothing", () => {
    const prev = new Set([3, 4]);
    expect(reduceMountedPages(prev, [{ pageNumber: 3, isIntersecting: true }])).toBe(prev);
  });

  it("adds entering pages and drops leaving ones in a single batch", () => {
    const next = reduceMountedPages(new Set([3]), [
      { pageNumber: 3, isIntersecting: false },
      { pageNumber: 7, isIntersecting: true },
    ]);
    expect([...next]).toEqual([7]);
  });

  it("ignores an entry whose slot carried no page number", () => {
    const prev = new Set([2]);
    expect(reduceMountedPages(prev, [{ pageNumber: NaN, isIntersecting: true }])).toBe(prev);
  });
});
