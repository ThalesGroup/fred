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

// Regression coverage: DocumentViewer's markdown fetch effect used to have no
// cancellation guard, so switching `documentUid` before the in-flight fetch
// resolved let a slower, superseded response win the race and overwrite the
// newer document's content (and its derived-title callback) via a stale
// `.then()`. Fixed by tracking a `cancelled` flag in the effect's cleanup.

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MetadataPreview } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// MarkdownRenderer pulls in mermaid/katex/react-markdown — irrelevant to this
// race and heavy to render. Stub it down to the one thing this test asserts on:
// the raw text it was handed.
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <p data-testid="content">{text}</p>,
}));

// Deferred promises so each documentUid's fetch can be resolved independently,
// in whatever order the test chooses — that's how we force the out-of-order
// resolution the real bug depended on.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const pending = new Map<string, ReturnType<typeof deferred<string>>>();
const fetchPreview = vi.fn((arg: { id: string; artifact: string }) => {
  let entry = pending.get(arg.id);
  if (!entry) {
    entry = deferred<string>();
    pending.set(arg.id, entry);
  }
  return { unwrap: () => entry.promise };
});

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useLazyPreviewQuery: () => [fetchPreview],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The PDF path pulls in react-pdf and a pdf.js worker; the markdown-mode tests
// only need to observe WHICH renderer was chosen.
vi.mock("../../../../../common/PdfStreamingDocumentViewer", () => ({
  PdfStreamingDocumentViewer: ({ documentUid }: { documentUid: string }) => (
    <p data-testid="pdf">{`pdf:${documentUid}`}</p>
  ),
}));

import { DocumentViewer } from "./DocumentViewer";

let container: HTMLDivElement;
let root: Root;

function renderViewer(documentUid: string, onLoaded: (content: string) => void) {
  act(() => {
    root.render(<DocumentViewer documentUid={documentUid} onMarkdownLoaded={onLoaded} />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  pending.clear();
  fetchPreview.mockClear();
});

describe("DocumentViewer — stale fetch race (out-of-order resolution)", () => {
  it("never lets a slower response for a superseded documentUid overwrite the current one", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    const loadedWith: string[] = [];
    const onLoaded = (content: string) => loadedWith.push(content);

    // 1. Open document A — its fetch is now in flight.
    renderViewer("doc-A", onLoaded);
    expect(fetchPreview).toHaveBeenCalledWith({ id: "doc-A", artifact: "raw" });

    // 2. Before A resolves, switch to document B — A's effect cleanup should
    // mark it cancelled; B's fetch is now in flight too.
    renderViewer("doc-B", onLoaded);
    expect(fetchPreview).toHaveBeenCalledWith({ id: "doc-B", artifact: "raw" });

    // 3. B resolves first (plausible: smaller payload / warm cache).
    await act(async () => {
      pending.get("doc-B")!.resolve("content-B");
      await pending.get("doc-B")!.promise;
    });
    expect(container.querySelector('[data-testid="content"]')?.textContent).toBe("content-B");

    // 4. A resolves after B, despite being requested first. Without the
    // cancellation guard this used to overwrite B's already-committed content.
    await act(async () => {
      pending.get("doc-A")!.resolve("content-A");
      await pending.get("doc-A")!.promise;
    });

    expect(container.querySelector('[data-testid="content"]')?.textContent).toBe("content-B");
    // The superseded A response must never have reached the onLoaded callback either
    // — only B's title-derivation call should have fired.
    expect(loadedWith).toEqual(["content-B"]);
  });
});

// The preview drawer's markdown toggle: a PDF must be able to show its markdown
// extraction on demand, and fall back to a readable empty state when the
// ingestion never produced one (the endpoint 404s).
describe("DocumentViewer — markdown mode for a natively-rendered file", () => {
  function render(node: ReactNode) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(node);
    });
  }

  it("renders the PDF viewer for a .pdf when no view is passed (default)", () => {
    render(<DocumentViewer documentUid="doc-pdf" fileName="facture.pdf" />);
    expect(container.querySelector('[data-testid="pdf"]')?.textContent).toBe("pdf:doc-pdf");
  });

  it("renders the markdown extraction for that same .pdf when view is raw", async () => {
    render(<DocumentViewer documentUid="doc-pdf" fileName="facture.pdf" view="raw" />);
    expect(container.querySelector('[data-testid="pdf"]')).toBeNull();
    expect(fetchPreview).toHaveBeenCalledWith({ id: "doc-pdf", artifact: "raw" });

    await act(async () => {
      pending.get("doc-pdf")!.resolve("# Facture");
      await pending.get("doc-pdf")!.promise;
    });
    expect(container.querySelector('[data-testid="content"]')?.textContent).toBe("# Facture");
  });

  it("shows an unavailable notice — not document text — when no markdown was generated", async () => {
    render(<DocumentViewer documentUid="doc-nomd" fileName="facture.pdf" view="raw" />);
    await act(async () => {
      pending.get("doc-nomd")!.reject(new Error("404"));
      await pending.get("doc-nomd")!.promise.catch(() => undefined);
    });

    expect(container.querySelector('[data-testid="content"]')).toBeNull();
    expect(container.textContent).toContain("rework.resources.preview.markdownUnavailable");
  });
});

describe("DocumentViewer - structured email facts", () => {
  it("reads the published metadata with conversation scope and renders facts as text", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const loaded = vi.fn();
    act(() =>
      root.render(
        <DocumentViewer
          documentUid="mail"
          sessionId="conversation"
          fileName="message.EML"
          view="metadata"
          onMarkdownLoaded={loaded}
        />,
      ),
    );
    expect(fetchPreview).toHaveBeenCalledWith({ id: "mail", artifact: "metadata", sessionId: "conversation" });
    await act(async () => {
      pending.get("mail")!.resolve(
        JSON.stringify({
          identity: { title: '<img src=x onerror="attack()">', author: "Paul", created: "2026-10-27T10:30:00+01:00" },
          extensions: { email: { to: ["Alice", "Bob"], cc: [], message_id: "<external>", in_reply_to: null } },
        } satisfies MetadataPreview),
      );
    });
    expect(container.textContent).toContain('<img src=x onerror="attack()">');
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("Paul");
    expect(container.textContent).toContain("Alice; Bob");
    expect(container.textContent).toContain("2026-10-27T10:30:00+01:00");
    expect(container.textContent).toContain("rework.resources.preview.email.missing");
    expect(loaded).not.toHaveBeenCalled();
  });

  it("keeps old documents without extracted headers readable with an explicit empty state", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<DocumentViewer documentUid="old-mail" fileName="message.msg" view="metadata" />));
    await act(async () => {
      pending.get("old-mail")!.resolve(JSON.stringify({ identity: {}, extensions: null }));
    });
    expect(container.textContent).toContain("rework.resources.preview.email.unavailable");
  });
});
