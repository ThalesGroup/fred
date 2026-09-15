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
import type { WikiRevisionList, WikiRevisionSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { emptyHistoryPages, mergeHistoryPage, type HistoryPages } from "./historyPages";

const revision = (id: string): WikiRevisionSummary => ({
  revision_id: id,
  status: "published",
  author_user_id: "alice",
  author_kind: "human",
});

const page = (ids: string[], nextCursor: string | null = null): WikiRevisionList => ({
  revisions: ids.map(revision),
  contents: Object.fromEntries(ids.map((id) => [id, `body-${id}`])),
  next_cursor: nextCursor,
});

describe("mergeHistoryPage", () => {
  it("replaces outright on a base page (first load)", () => {
    const result = mergeHistoryPage(emptyHistoryPages, undefined, page(["r1", "r2"], "cursor-1"));
    expect(result.revisions.map((r) => r.revision_id)).toEqual(["r1", "r2"]);
    expect(result.nextCursor).toBe("cursor-1");
  });

  it("appends a subsequent page onto the accumulated tail", () => {
    const first = mergeHistoryPage(emptyHistoryPages, undefined, page(["r1", "r2"], "cursor-1"));
    const second = mergeHistoryPage(first, "cursor-1", page(["r3", "r4"], null));

    expect(second.revisions.map((r) => r.revision_id)).toEqual(["r1", "r2", "r3", "r4"]);
    expect(second.contents).toMatchObject({ r1: "body-r1", r3: "body-r3" });
    expect(second.nextCursor).toBeNull();
  });

  it("deduplicates by revision_id when a page overlaps what is already held", () => {
    const first = mergeHistoryPage(emptyHistoryPages, undefined, page(["r1", "r2"], "cursor-1"));
    // A retried "load older" returning the same page again must not double it.
    const second = mergeHistoryPage(first, "cursor-1", page(["r2", "r3"], null));

    expect(second.revisions.map((r) => r.revision_id)).toEqual(["r1", "r2", "r3"]);
  });

  it("replaces rather than mixes when a BASE page arrives after older pages were already loaded", () => {
    // This is the invalidation case: the reader had paged down to r4, then a
    // restore (or any other write) invalidates the query and the base page
    // (cursor=undefined) refetches. The old tail (r3, r4) must be dropped,
    // not blended with the fresh top.
    const walked: HistoryPages = mergeHistoryPage(
      mergeHistoryPage(emptyHistoryPages, undefined, page(["r1", "r2"], "cursor-1")),
      "cursor-1",
      page(["r3", "r4"], null),
    );
    expect(walked.revisions).toHaveLength(4);

    const afterInvalidation = mergeHistoryPage(walked, undefined, page(["r0", "r1"], "cursor-1"));
    expect(afterInvalidation.revisions.map((r) => r.revision_id)).toEqual(["r0", "r1"]);
  });

  it("carries null forward when a page reports no further history", () => {
    const result = mergeHistoryPage(emptyHistoryPages, undefined, page(["r1"]));
    expect(result.nextCursor).toBeNull();
  });
});
