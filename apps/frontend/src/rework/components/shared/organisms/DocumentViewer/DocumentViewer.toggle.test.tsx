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

// Coverage for the FRONT-09.H "Fichier"/"Raw" toggle. The toggle itself
// (DocumentViewerModeToggle) is rendered by the host, not by DocumentViewer —
// the corpus preview drawer places it in its own header, left of the close
// button, instead of stealing a row from the document body. DocumentViewer
// only picks content per the controlled `view` prop.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: () => <p data-testid="markdown-view" />,
}));
vi.mock("../../../../../common/PdfStreamingDocumentViewer", () => ({
  PdfStreamingDocumentViewer: () => <div data-testid="pdf-view" />,
}));
// A real RTK Query lazy-query trigger is a stable function across renders —
// a fresh closure here on every render (as a plain `() => [...]` factory
// would give) makes MarkdownDocumentBody's fetch effect (dependent on this
// function's identity) refire every render, looping forever.
const fetchPreviewMock = vi.hoisted(() => vi.fn(() => ({ unwrap: () => Promise.resolve({ content: "" }) })));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery: () => [fetchPreviewMock],
}));

import { DocumentViewer, DocumentViewerModeToggle } from "./DocumentViewer.tsx";

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

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

/** MarkdownDocumentBody fetches its content asynchronously (starts in a
 * "Loading…" state) — flush that microtask before asserting on the markdown
 * view. */
async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("DocumentViewer Fichier/Raw content", () => {
  it("renders the PDF natively with no toggle when view is omitted (existing callers)", () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" />);
    expect(container.querySelector('[data-testid="pdf-view"]')).not.toBeNull();
    expect(container.querySelector('[role="tablist"]')).toBeNull();
  });

  it('renders the native PDF for view="file", with no toggle of its own', () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" view="file" />);
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector('[data-testid="pdf-view"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="markdown-view"]')).toBeNull();
  });

  it('renders the markdown extraction for view="raw"', async () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" view="raw" />);
    await flush();
    expect(container.querySelector('[data-testid="pdf-view"]')).toBeNull();
    expect(container.querySelector('[data-testid="markdown-view"]')).not.toBeNull();
  });

  it("ignores `view` for a non-PDF file — there is nothing to switch to", async () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.docx" view="raw" />);
    await flush();
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector('[data-testid="markdown-view"]')).not.toBeNull();
  });
});

describe("DocumentViewerModeToggle", () => {
  it("reports the clicked mode via onChange", () => {
    const onChange = vi.fn();
    render(<DocumentViewerModeToggle view="file" onChange={onChange} />);

    const tabs = Array.from(container.querySelectorAll('[role="tab"]'));
    expect(tabs).toHaveLength(2);
    click(tabs[1]); // "Raw"

    expect(onChange).toHaveBeenCalledWith("raw");
  });

  it("marks the current view's tab as selected", () => {
    render(<DocumentViewerModeToggle view="raw" onChange={() => {}} />);
    const tabs = Array.from(container.querySelectorAll('[role="tab"]'));
    expect(tabs[0].getAttribute("aria-selected")).toBe("false");
    expect(tabs[1].getAttribute("aria-selected")).toBe("true");
  });
});
