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
import type { WikiRevisionSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { historyEntries } from "./historyEntries";

const revision = (over: Partial<WikiRevisionSummary> & { revision_id: string }): WikiRevisionSummary => ({
  status: "published",
  author_user_id: "alice",
  author_kind: "human",
  ...over,
});

describe("historyEntries", () => {
  it("splits a validated revision into the edit and the validation", () => {
    const entries = historyEntries([
      revision({
        revision_id: "r1",
        author_kind: "agent",
        created_at: "2026-09-06T10:00:00+00:00",
        reviewed_at: "2026-09-06T11:00:00+00:00",
        reviewed_by: "bob",
      }),
    ]);

    expect(entries.map((e) => e.kind)).toEqual(["review", "revision"]);
    const [review] = entries;
    expect(review).toMatchObject({ kind: "review", by: "bob", ofAgentEdit: true });
  });

  it("orders a validation against later revisions by when it happened", () => {
    // The validation of r1 lands BETWEEN r1 and r2 — folding it into r1's own
    // entry would have put it in the wrong place on the timeline.
    const entries = historyEntries([
      revision({ revision_id: "r2", created_at: "2026-09-06T12:00:00+00:00" }),
      revision({
        revision_id: "r1",
        author_kind: "agent",
        created_at: "2026-09-06T10:00:00+00:00",
        reviewed_at: "2026-09-06T11:00:00+00:00",
        reviewed_by: "bob",
      }),
    ]);

    expect(entries.map((e) => e.key)).toEqual(["r2", "r1:review", "r1"]);
  });

  it("emits no validation entry for a revision nobody has validated", () => {
    const entries = historyEntries([revision({ revision_id: "r1", created_at: "2026-09-06T10:00:00+00:00" })]);
    expect(entries).toHaveLength(1);
  });

  it("sorts a revision with no timestamp last rather than first", () => {
    const entries = historyEntries([
      revision({ revision_id: "undated" }),
      revision({ revision_id: "r1", created_at: "2026-09-06T10:00:00+00:00" }),
    ]);
    expect(entries.map((e) => e.key)).toEqual(["r1", "undated"]);
  });
});
