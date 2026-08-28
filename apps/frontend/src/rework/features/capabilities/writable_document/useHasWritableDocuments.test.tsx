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

// Two sources answer "does this conversation have a document?" and each is blind
// on its own: the list API lags a live agent write by one refetch, and the live
// snapshots outlive the conversation that produced them (the slice only drops
// them on its next upsert). Both halves have to be right or the launcher either
// misses a fresh write or lingers on an empty chat.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { WritableDocumentState } from "./writableDocumentSlice";
import type { WritableDocumentPartData } from "./types";

const state = vi.hoisted(() => ({
  session: "",
  doc: null as unknown,
  // What the query resolved for, and what it resolved to - so a stale answer from
  // a previous conversation is expressible, the way RTK Query's `data` exposes one.
  listedFor: "",
  listed: undefined as unknown,
  // Whether the catalog/prep answer that carries the pod's base URL has landed.
  routed: true,
}));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(state.session ? `session=${state.session}` : "")],
}));

vi.mock("react-redux", () => ({
  useSelector: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      writableDocument: state.doc,
      capabilityRouting: { baseUrls: state.routed ? { writable_document: "https://pod" } : {} },
    }),
}));

vi.mock("./api/writableDocumentCapabilityOpenApi", () => ({
  // `data` keeps the last resolved result across an arg change; `currentData` is
  // undefined until the answer belongs to the CURRENT args. Modelling both is what
  // makes the stale-conversation case below fail on the wrong one.
  useListWritableDocumentsQuery: (args: { sessionId: string }, opts: { skip: boolean }) => ({
    data: opts.skip ? undefined : state.listed,
    currentData: opts.skip || state.listedFor !== args.sessionId ? undefined : state.listed,
  }),
}));

const { useHasWritableDocuments } = await import("./useHasWritableDocuments");

const liveDoc = { document_id: "d1", title: "Notes", content_md: "" } as WritableDocumentPartData;

function sliceState(sessionId: string | null, docs: WritableDocumentPartData[]): WritableDocumentState {
  return {
    sessionId,
    liveById: Object.fromEntries(docs.map((d) => [d.document_id, d])),
    selectedId: null,
  };
}

function read(
  openSession: string,
  doc: WritableDocumentState,
  listed: unknown,
  listedFor = openSession,
  routed = true,
): boolean {
  let seen = false;
  state.session = openSession;
  state.doc = doc;
  state.listed = listed;
  state.listedFor = listedFor;
  state.routed = routed;
  function Probe() {
    seen = useHasWritableDocuments();
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return seen;
}

const empty = sliceState(null, []);

describe("useHasWritableDocuments", () => {
  it("is false on a conversation with no document", () => {
    expect(read("s1", empty, [])).toBe(false);
  });

  it("is true once the list API reports a document", () => {
    expect(read("s1", empty, [{ document_id: "d1" }])).toBe(true);
  });

  it("is true on a live agent write the list has not caught up with yet", () => {
    expect(read("s1", sliceState("s1", [liveDoc]), [])).toBe(true);
  });

  it("ignores live snapshots left over from another conversation", () => {
    expect(read("s2", sliceState("s1", [liveDoc]), [])).toBe(false);
  });

  it("is false while the list answer has not arrived", () => {
    expect(read("s1", empty, undefined)).toBe(false);
  });

  it("ignores the list answer still held from the conversation just left", () => {
    expect(read("s2", empty, [{ document_id: "d1" }], "s1")).toBe(false);
  });

  it("holds the query until the capability's pod base URL is known", () => {
    // Fired before it lands, the query fails on args that never change again and
    // the launcher stays dark for the whole page load (hard reload only - a
    // client-side navigation finds routing already in the store).
    expect(read("s1", empty, [{ document_id: "d1" }], "s1", false)).toBe(false);
  });

  it("is false while no conversation is open", () => {
    expect(read("", sliceState("s1", [liveDoc]), [{ document_id: "d1" }])).toBe(false);
  });
});
