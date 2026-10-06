// @vitest-environment jsdom
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

import { act, createElement } from "react";
import type { MDXEditorMethods, MDXEditorProps } from "@mdxeditor/editor";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WritableDocumentResponse } from "./api/writableDocumentCapabilityOpenApi";

const state = vi.hoisted(() => ({
  documents: [] as WritableDocumentResponse[],
  methods: null as MDXEditorMethods | null,
  sanitize: vi.fn(),
  onChange: undefined as MDXEditorProps["onChange"],
  importError: vi.fn(),
  update: vi.fn((_request: unknown) => ({ unwrap: async () => undefined })),
  refetch: vi.fn(),
}));

vi.mock("./sanitizeEditorMarkdown", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./sanitizeEditorMarkdown")>();
  return {
    sanitizeEditorMarkdown: (markdown: string) => {
      state.sanitize(markdown);
      return actual.sanitizeEditorMarkdown(markdown);
    },
  };
});

vi.mock("@mdxeditor/editor", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@mdxeditor/editor")>();
  return {
    ...actual,
    MDXEditor: (props: MDXEditorProps) => {
      state.onChange = props.onChange;
      return createElement(actual.MDXEditor, {
        ...props,
        onError: state.importError,
        ref: (methods) => {
          state.methods = methods;
        },
      });
    },
  };
});

vi.mock("react-redux", () => ({
  useDispatch: () => () => undefined,
  useSelector: (selector: (value: unknown) => unknown) =>
    selector({
      writableDocument: { sessionId: null, liveById: {}, selectedId: null },
      capabilityRouting: { baseUrls: { writable_document: "https://pod" } },
    }),
}));
vi.mock("./api/writableDocumentCapabilityOpenApi", () => ({
  useListWritableDocumentsQuery: () => ({ currentData: state.documents, refetch: state.refetch }),
  useUpdateWritableDocumentMutation: () => [state.update],
}));
vi.mock("./WritableDocumentDownloadButton", () => ({
  default: () => <button type="button">Download</button>,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { WritableDocumentPane } = await import("./WritableDocumentPane");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
const markdown = "# RAGuard\n\n- **Latency**: Minimal overhead (<3ms for dense retrieval).";
const doc = (overrides: Partial<WritableDocumentResponse> = {}): WritableDocumentResponse => ({
  session_id: "s1",
  document_id: "d1",
  title: "RAGuard",
  content_md: markdown,
  updated_by: "agent",
  updated_at: "2026-10-06T12:48:16Z",
  ...overrides,
});

async function render() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={["/?session=s1"]}>
        <WritableDocumentPane capabilityId="writable_document" onClose={() => undefined} />
      </MemoryRouter>,
    );
  });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  vi.clearAllMocks();
  state.documents = [doc()];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
});

describe("WritableDocumentPane Markdown import", () => {
  it("renders literal comparisons in the rich-text editor without saving initialization", async () => {
    await render();
    expect(container.querySelector("textarea")).toBeNull();
    expect(container.querySelector('[contenteditable="true"]')?.textContent).toContain(
      "Latency: Minimal overhead (<3ms for dense retrieval).",
    );
    expect(container.querySelector("h1")?.textContent).toBe("RAGuard");
    expect(container.querySelector("strong")?.textContent).toBe("Latency");
    expect(container.textContent).toContain("Download");
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();
  });

  it("autosaves user edits but ignores the editor's initial Markdown normalization", async () => {
    await render();
    await act(async () => state.onChange?.("normalized initial content", true));
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();

    const edited = "# Edited summary\n\nLatency is less than 3ms.";
    await act(async () => state.onChange?.(edited, false));
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).toHaveBeenCalledExactlyOnceWith({
      sessionId: "s1",
      documentId: "d1",
      writableDocumentUpdate: { content_md: edited },
    });
  });

  it("preserves inline code, HTML and clickable autolinks", async () => {
    state.documents = [doc({ content_md: "Use `<3ms` and k<sub>safe</sub>. See <https://example.test>." })];
    await render();
    expect(container.querySelector('[contenteditable="true"]')?.textContent).toContain("Use <3ms and ksafe.");
    expect(container.querySelector('[contenteditable="true"] code')?.textContent).toBe("<3ms");
    expect(container.querySelector('[contenteditable="true"] sub')?.textContent).toBe("safe");
    expect(container.querySelector('[contenteditable="true"] a')?.getAttribute("href")).toBe("https://example.test");
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();
  });

  it("renders another document and a new agent revision with fresh sanitized content", async () => {
    await render();
    state.documents = [doc({ content_md: "# Revised summary\n\nLatency <2ms.", updated_at: "2026-10-06T12:49:00Z" })];
    await render();
    expect(container.querySelector('[contenteditable="true"]')?.textContent).toContain("Latency <2ms.");

    state.documents = [doc({ document_id: "d2", content_md: "# Another document\n\nLatency <1ms." })];
    await render();
    expect(container.querySelector('[contenteditable="true"]')?.textContent).toContain("Latency <1ms.");
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();
  });

  it("preserves image alt text containing a comparison", async () => {
    state.documents = [doc({ content_md: "![Latency <3ms](https://example.test/graph.png)" })];
    await render();
    expect(container.querySelector('[contenteditable="true"]')).not.toBeNull();
    expect(state.importError).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();
  });

  it("keeps real HTML tags alongside literal comparisons", async () => {
    state.documents = [doc({ content_md: "<div><strong>Important</strong> Latency <3ms.</div>" })];
    await render();
    expect(state.importError).not.toHaveBeenCalled();
    expect(container.querySelector('[contenteditable="true"] strong')?.textContent).toBe("Important");
    expect(container.querySelector('[contenteditable="true"]')?.textContent).toContain("Latency <3ms.");
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).not.toHaveBeenCalled();
  });
  it.each([
    ["<https://example.test/a*b*c>", "https://example.test/a*b*c", "https://example.test/a*b*c"],
    ["<a*b*c@example.test>", "a*b*c@example.test", "mailto:a*b*c@example.test"],
    ["<https://example.test/?q=&amp;>", "https://example.test/?q=&amp;", "https://example.test/?q=&amp;"],
  ])("preserves literal autolink data: %s", async (content_md, label, href) => {
    state.documents = [doc({ content_md })];
    await render();
    const link = container.querySelector('[contenteditable="true"] a');
    expect(link?.textContent).toBe(label);
    expect(link?.getAttribute("href")).toBe(href);
    expect(state.importError).not.toHaveBeenCalled();
  });

  it("prepares only on import and autosaves actual rich-text edits", async () => {
    await render();
    expect(state.sanitize).toHaveBeenCalledExactlyOnceWith(markdown);
    await act(async () => {
      state.methods?.focus();
      state.methods?.insertMarkdown("An actual editor edit.");
    });
    await act(async () => vi.advanceTimersByTimeAsync(800));
    expect(state.update).toHaveBeenCalled();
    expect(state.update.mock.calls[0]?.[0]).toMatchObject({
      writableDocumentUpdate: { content_md: expect.stringContaining("An actual editor edit.") },
    });
    expect(state.sanitize).toHaveBeenCalledTimes(1);
  });
  it("preserves code inside HTML when importing and exporting", async () => {
    state.documents = [doc({ content_md: "<div>`<foo> <3ms`</div>" })];
    await render();
    expect(state.importError).not.toHaveBeenCalled();
    expect(container.querySelector('[contenteditable="true"] code')?.textContent).toBe("<foo> <3ms");
    expect(state.methods?.getMarkdown()).toContain("`<foo> <3ms`");
  });
});
