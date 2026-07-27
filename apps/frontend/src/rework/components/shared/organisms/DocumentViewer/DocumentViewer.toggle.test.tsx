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

// Coverage for the FRONT-09.H "Fichier"/"Raw" toggle: a PDF renders natively
// by default (unchanged behavior for existing callers) and only shows the
// toggle when a host explicitly opts in via showRawToggle.

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
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery: () => [
    () => ({ unwrap: () => Promise.resolve({ content: "" }) }),
  ],
}));

import { DocumentViewer } from "./DocumentViewer.tsx";

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

describe("DocumentViewer Fichier/Raw toggle", () => {
  it("renders the PDF natively with no toggle when showRawToggle is omitted (existing callers)", () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" />);
    expect(container.querySelector('[data-testid="pdf-view"]')).not.toBeNull();
    expect(container.querySelector('[role="tablist"]')).toBeNull();
  });

  it("shows the toggle for a PDF when showRawToggle is set, defaulting to the file view", () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" showRawToggle />);
    expect(container.querySelector('[role="tablist"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="pdf-view"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="markdown-view"]')).toBeNull();
  });

  it("switches away from the native PDF render when Raw is clicked", () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.pdf" showRawToggle />);
    const tabs = Array.from(container.querySelectorAll('[role="tab"]'));
    click(tabs[1]); // "Raw"
    expect(container.querySelector('[data-testid="pdf-view"]')).toBeNull();
  });

  it("never shows the toggle for a non-PDF file — there is nothing to switch to", () => {
    render(<DocumentViewer documentUid="doc-1" fileName="report.docx" showRawToggle />);
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector('[data-testid="pdf-view"]')).toBeNull();
  });
});
