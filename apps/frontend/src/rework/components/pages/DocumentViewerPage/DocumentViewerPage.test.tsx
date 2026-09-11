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

// A citation opens a document at the passage it quotes, and that passage lives in
// the markdown extraction. Once office documents gained a native render, this page
// had to keep a route back to that extraction — otherwise a render failure leaves
// the reader staring at an error where the cited text used to be.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ uid: "doc-1" }),
  useSearchParams: () => [searchParams.current],
  useNavigate: () => vi.fn(),
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer", () => ({
  DocumentViewer: ({ view }: { view?: string }) => <div data-testid="viewer" data-view={view ?? "none"} />,
  DocumentViewerModeToggle: ({ onChange }: { onChange: (v: string) => void }) => (
    <button data-testid="mode-toggle" onClick={() => onChange("raw")} />
  ),
}));

import DocumentViewerPage from "./DocumentViewerPage.tsx";

let container: HTMLDivElement;
let root: Root;

function renderFor(fileName: string) {
  searchParams.current = new URLSearchParams({ file: fileName });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<DocumentViewerPage />);
  });
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("DocumentViewerPage", () => {
  it("offers a way back to the markdown extraction for a Word citation", () => {
    renderFor("rapport.docx");

    const toggle = container.querySelector('[data-testid="mode-toggle"]');
    expect(toggle).not.toBeNull();
    expect(container.querySelector('[data-testid="viewer"]')?.getAttribute("data-view")).toBe("file");

    act(() => {
      toggle?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(container.querySelector('[data-testid="viewer"]')?.getAttribute("data-view")).toBe("raw");
  });

  it("offers no toggle for a format that only ever renders as markdown", () => {
    renderFor("ventes.csv");

    expect(container.querySelector('[data-testid="mode-toggle"]')).toBeNull();
    // `view` stays undefined so DocumentViewer keeps its single-strategy behaviour.
    expect(container.querySelector('[data-testid="viewer"]')?.getAttribute("data-view")).toBe("none");
  });
});
