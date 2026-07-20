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

// writable_document plugin registration + slice reducer (#1905).

import { describe, expect, it } from "vitest";
import { rendererForPartKind } from "../partRendererRegistry";
import { sidePanelsForCapabilities } from "../sidePanelRegistry";
import { WritableDocumentCardRenderer } from "./WritableDocumentCardRenderer";
import { WritableDocumentPane } from "./WritableDocumentPane";
import type { WritableDocumentPartData } from "./types";
import reducer, {
  clearWritableDocuments,
  selectWritableDocument,
  upsertFromPart,
  type WritableDocumentState,
} from "./writableDocumentSlice";

const part = (over: Partial<WritableDocumentPartData> = {}): WritableDocumentPartData => ({
  type: "writable_document",
  document_id: "d1",
  title: "Draft",
  content_md: "# hi",
  updated_at: "2026-07-20T10:00:00Z",
  updated_by: "agent",
  ...over,
});

describe("writable_document plugin registration", () => {
  it("registers the writable_document chat-part renderer through the real index", () => {
    expect(rendererForPartKind("writable_document")).toBe(WritableDocumentCardRenderer);
  });

  it("contributes the writable_document_pane side panel when the capability is active", () => {
    const entries = sidePanelsForCapabilities(["writable_document"]);
    expect(entries).toContainEqual(
      expect.objectContaining({
        capabilityId: "writable_document",
        widget: "writable_document_pane",
        Component: WritableDocumentPane,
      }),
    );
  });
});

describe("writableDocumentSlice", () => {
  it("keeps the newest updated_at per document_id (a stale snapshot never masks a fresher write)", () => {
    let state = reducer(undefined, upsertFromPart({ sessionId: "s1", doc: part({ content_md: "old" }) }));
    // A newer write supersedes the old content.
    state = reducer(
      state,
      upsertFromPart({ sessionId: "s1", doc: part({ content_md: "new", updated_at: "2026-07-20T11:00:00Z" }) }),
    );
    expect(state.liveById.d1.content_md).toBe("new");
    // An out-of-order OLDER snapshot arriving later must NOT overwrite the newer one.
    state = reducer(
      state,
      upsertFromPart({ sessionId: "s1", doc: part({ content_md: "stale", updated_at: "2026-07-20T09:00:00Z" }) }),
    );
    expect(state.liveById.d1.content_md).toBe("new");
  });

  it("resets the live map when a snapshot from a different session arrives", () => {
    let state = reducer(undefined, upsertFromPart({ sessionId: "s1", doc: part({ document_id: "a" }) }));
    state = reducer(state, upsertFromPart({ sessionId: "s2", doc: part({ document_id: "b" }) }));
    expect(Object.keys(state.liveById)).toEqual(["b"]);
    expect(state.sessionId).toBe("s2");
  });

  it("tracks the selected document and clears everything on teardown", () => {
    let state: WritableDocumentState = reducer(undefined, upsertFromPart({ sessionId: "s1", doc: part() }));
    state = reducer(state, selectWritableDocument("d1"));
    expect(state.selectedId).toBe("d1");
    state = reducer(state, clearWritableDocuments());
    expect(state).toEqual({ sessionId: null, liveById: {}, selectedId: null });
  });
});
