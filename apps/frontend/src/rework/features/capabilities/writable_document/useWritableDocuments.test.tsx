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

// Which documents the editor offers as tabs.
//
// The set is a merge of two sources that expire differently: the API list is
// scoped to the conversation asked for, while the live snapshots sit in a global
// slice the next conversation only clears when it upserts one of its own. A
// conversation whose documents all come from the API never upserts, so an
// unguarded merge showed the PREVIOUS conversation's document as an extra tab -
// someone else's document, in an editor that autosaves.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { WritableDocumentPartData } from "./types";
import type { WritableDocumentView } from "./useWritableDocuments";

const state = vi.hoisted(() => ({
  live: null as unknown,
  listedFor: "",
  listed: [] as unknown[],
}));

vi.mock("react-redux", () => ({
  useDispatch: () => () => undefined,
  useSelector: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      writableDocument: state.live,
      capabilityRouting: { baseUrls: { writable_document: "https://pod" } },
    }),
}));

vi.mock("./api/writableDocumentCapabilityOpenApi", () => ({
  useListWritableDocumentsQuery: (args: { sessionId: string }, opts: { skip: boolean }) => ({
    data: opts.skip ? undefined : state.listed,
    currentData: opts.skip || state.listedFor !== args.sessionId ? undefined : state.listed,
    refetch: () => undefined,
  }),
  useUpdateWritableDocumentMutation: () => [() => ({ unwrap: async () => undefined })],
}));

const { useWritableDocuments } = await import("./useWritableDocuments");

const doc = (id: string, title: string) =>
  ({ document_id: id, title, content_md: "", updated_at: "2026-08-28T10:00:00Z" }) as WritableDocumentPartData;

function titlesFor(openSession: string, liveSessionId: string | null, live: WritableDocumentPartData[]): string[] {
  state.live = {
    sessionId: liveSessionId,
    liveById: Object.fromEntries(live.map((d) => [d.document_id, d])),
    selectedId: null,
  };
  let seen: WritableDocumentView[] = [];
  function Probe() {
    seen = useWritableDocuments(openSession).documents;
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return seen.map((d) => d.title).sort();
}

describe("useWritableDocuments", () => {
  it("offers the live snapshots of the open conversation", () => {
    state.listedFor = "s1";
    state.listed = [];

    expect(titlesFor("s1", "s1", [doc("d1", "Résumé des logs")])).toEqual(["Résumé des logs"]);
  });

  it("never offers a document left over from another conversation", () => {
    state.listedFor = "s2";
    state.listed = [doc("d2", "Résumé des logs")];

    // The slice still holds s1's document: s2's came from the API, so nothing
    // upserted and nothing reset the map.
    expect(titlesFor("s2", "s1", [doc("d1", "Le Bitcoin en 3 lignes")])).toEqual(["Résumé des logs"]);
  });

  it("offers nothing while the list still answers for the conversation just left", () => {
    state.listedFor = "s1";
    state.listed = [doc("d1", "Le Bitcoin en 3 lignes")];

    expect(titlesFor("s2", null, [])).toEqual([]);
  });
});
