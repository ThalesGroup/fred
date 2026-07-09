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

import { describe, expect, it } from "vitest";
import type { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { pagesToRefreshOnTaskCompletion } from "./refreshOnCompletion.ts";

const doc = (uid: string): DocumentMetadata => ({ identity: { document_uid: uid } }) as unknown as DocumentMetadata;

const page = (offset: number, ...uids: string[]) => ({ offset, docs: uids.map(doc) });

describe("pagesToRefreshOnTaskCompletion", () => {
  it("returns nothing when the running set is unchanged (no transition)", () => {
    const running = new Set(["a"]);
    expect(pagesToRefreshOnTaskCompletion(running, running, { t1: page(0, "a") })).toEqual([]);
  });

  it("refetches the page holding a document whose task just finished", () => {
    const prev = new Set(["a"]);
    const now = new Set<string>();
    expect(pagesToRefreshOnTaskCompletion(prev, now, { t1: page(0, "a", "b") })).toEqual([{ tagId: "t1", offset: 0 }]);
  });

  it("refetches only pages that actually contain the finished document, preserving offset", () => {
    const prev = new Set(["a"]);
    const now = new Set<string>();
    const result = pagesToRefreshOnTaskCompletion(prev, now, {
      t1: page(50, "a"),
      t2: page(0, "x", "y"),
    });
    expect(result).toEqual([{ tagId: "t1", offset: 50 }]);
  });

  it("does not refetch while the document is still running", () => {
    const prev = new Set(["a"]);
    const now = new Set(["a"]);
    expect(pagesToRefreshOnTaskCompletion(prev, now, { t1: page(0, "a") })).toEqual([]);
  });

  it("ignores an undefined target id in the running sets", () => {
    const prev = new Set<string | undefined>([undefined]);
    const now = new Set<string | undefined>();
    expect(pagesToRefreshOnTaskCompletion(prev, now, { t1: page(0, "a") })).toEqual([]);
  });

  it("handles several documents finishing across different pages", () => {
    const prev = new Set(["a", "b"]);
    const now = new Set<string>();
    const result = pagesToRefreshOnTaskCompletion(prev, now, {
      t1: page(0, "a"),
      t2: page(0, "b"),
    });
    expect(result).toEqual([
      { tagId: "t1", offset: 0 },
      { tagId: "t2", offset: 0 },
    ]);
  });
});
