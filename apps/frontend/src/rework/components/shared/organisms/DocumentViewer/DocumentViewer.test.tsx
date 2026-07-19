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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const pending = new Map<string, ReturnType<typeof deferred<{ content: string }>>>();
const fetchPreview = vi.fn((arg: { documentUid: string }) => {
  let entry = pending.get(arg.documentUid);
  if (!entry) {
    entry = deferred<{ content: string }>();
    pending.set(arg.documentUid, entry);
  }
  return { unwrap: () => entry.promise };
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery: () => [fetchPreview],
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
    expect(fetchPreview).toHaveBeenCalledWith({ documentUid: "doc-A" });

    // 2. Before A resolves, switch to document B — A's effect cleanup should
    // mark it cancelled; B's fetch is now in flight too.
    renderViewer("doc-B", onLoaded);
    expect(fetchPreview).toHaveBeenCalledWith({ documentUid: "doc-B" });

    // 3. B resolves first (plausible: smaller payload / warm cache).
    await act(async () => {
      pending.get("doc-B")!.resolve({ content: "content-B" });
      await pending.get("doc-B")!.promise;
    });
    expect(container.querySelector('[data-testid="content"]')?.textContent).toBe("content-B");

    // 4. A resolves after B, despite being requested first. Without the
    // cancellation guard this used to overwrite B's already-committed content.
    await act(async () => {
      pending.get("doc-A")!.resolve({ content: "content-A" });
      await pending.get("doc-A")!.promise;
    });

    expect(container.querySelector('[data-testid="content"]')?.textContent).toBe("content-B");
    // The superseded A response must never have reached the onLoaded callback either
    // — only B's title-derivation call should have fired.
    expect(loadedWith).toEqual(["content-B"]);
  });
});
