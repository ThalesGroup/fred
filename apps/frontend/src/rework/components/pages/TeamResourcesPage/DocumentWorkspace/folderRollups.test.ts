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

// Unit coverage for the folder rollup's pure half (#2384). These are the rules
// a rendered-workspace test cannot reach cheaply: outcome ranking across two
// clocks, unrankable timestamps, and the fact that ONE ranking decision governs
// both failure sources rather than only the task-derived one.

import { describe, expect, it } from "vitest";
import { buildFolderRollups, indexFoldersByDocUid, resolveDocOutcomes, type FailedDoc } from "./folderRollups";
import { buildTree } from "../../../../../shared/utils/tagTree";
import type { TaskSummary } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";

const history = (uid: string, state: string, updatedAt: string, label = `${uid}.pdf`) =>
  ({
    task_id: `h-${uid}-${state}`,
    kind: "ingestion",
    state,
    target: { type: "document", id: uid, label },
    created_at: updatedAt,
    updated_at: updatedAt,
  }) as unknown as TaskSummary;

const live = (uid: string, state: string, terminalAt: number, label = `${uid}.pdf`) =>
  ({
    taskId: `l-${uid}-${state}`,
    kind: "ingestion",
    state,
    target: { type: "document", id: uid, label },
    terminalAt,
    registeredAt: terminalAt,
  }) as unknown as TaskViewModel;

describe("resolveDocOutcomes", () => {
  it("keeps the newest history outcome per document", () => {
    const outcomes = resolveDocOutcomes(
      [history("doc", "failed", "2026-08-17T10:00:00Z"), history("doc", "succeeded", "2026-08-17T11:00:00Z")],
      [],
    );
    expect(outcomes.failed.has("doc")).toBe(false);
    expect(outcomes.resolved.has("doc")).toBe(true);
  });

  it("lets a live outcome win over history regardless of the clocks", () => {
    // The browser stamps the live store and the server stamps the history. A
    // laptop running behind would otherwise leave a repaired document flagged:
    // its success carries a smaller number than the failure it supersedes.
    const outcomes = resolveDocOutcomes(
      [history("doc", "failed", "2026-08-17T10:00:00Z")],
      [live("doc", "succeeded", Date.parse("2026-08-17T09:00:00Z"))],
    );
    expect(outcomes.failed.has("doc")).toBe(false);
  });

  it("does not let an unrankable timestamp pin the first entry seen", () => {
    const outcomes = resolveDocOutcomes(
      [history("doc", "failed", "not-a-date"), history("doc", "succeeded", "2026-08-17T11:00:00Z")],
      [],
    );
    expect(outcomes.failed.has("doc")).toBe(false);
  });

  it("treats cancelled as resolving a failure, never as one", () => {
    const outcomes = resolveDocOutcomes(
      [history("doc", "failed", "2026-08-17T10:00:00Z"), history("doc", "cancelled", "2026-08-17T11:00:00Z")],
      [],
    );
    expect(outcomes.failed.has("doc")).toBe(false);
    expect(outcomes.resolved.has("doc")).toBe(true);
  });

  it("ignores tasks still running and tasks that target something else", () => {
    const outcomes = resolveDocOutcomes(
      [
        history("doc", "running", "2026-08-17T10:00:00Z"),
        {
          ...history("x", "failed", "2026-08-17T10:00:00Z"),
          target: { type: "campaign", id: "c1", label: "c" },
        } as TaskSummary,
      ],
      [],
    );
    expect(outcomes.failed.size).toBe(0);
    expect(outcomes.resolved.size).toBe(0);
  });

  it("carries the document name from the winning outcome", () => {
    const outcomes = resolveDocOutcomes([history("doc", "failed", "2026-08-17T10:00:00Z", "Rapport.pdf")], []);
    expect(outcomes.failed.get("doc")?.name).toBe("Rapport.pdf");
  });

  it("carries the message the ingestion task reported", () => {
    // The only account of a run that died before any pipeline stage started —
    // `processing.errors` is keyed by stage and stays empty for it.
    const task = { ...history("doc", "failed", "2026-08-17T10:00:00Z"), error: "Worker timed out" } as TaskSummary;
    const outcomes = resolveDocOutcomes([task], []);
    expect(outcomes.failed.get("doc")?.error).toBe("Worker timed out");
  });
});

describe("indexFoldersByDocUid", () => {
  it("attributes a document buried in a sub-folder to the visible child folder", () => {
    const tree = buildTree([
      { id: "t-a", name: "A", path: "", type: "document", item_ids: ["doc-a"] },
      { id: "t-deep", name: "Deep", path: "A", type: "document", item_ids: ["doc-deep"] },
    ] as never);
    const index = indexFoldersByDocUid([...tree.children.values()]);
    expect(index.get("doc-a")).toBe("A");
    expect(index.get("doc-deep")).toBe("A");
  });
});

function rollupsFor(overrides: {
  failedDocsByTagId?: Map<string, FailedDoc[]>;
  outcomes?: { failed: Map<string, FailedDoc>; resolved: Set<string> };
  activeDocUids?: string[];
  justCompletedDocUids?: Set<string>;
  pendingTagIds?: string[];
}) {
  const tree = buildTree([{ id: "t-a", name: "A", path: "", type: "document", item_ids: ["doc-a"] }] as never);
  const childFolders = [...tree.children.values()];
  return buildFolderRollups({
    childFolders,
    tagIdsByFolder: new Map([["A", ["t-a"]]]),
    folderByDocUid: indexFoldersByDocUid(childFolders),
    pendingTagIds: overrides.pendingTagIds ?? [],
    failedDocsByTagId: overrides.failedDocsByTagId ?? new Map(),
    activeDocUids: overrides.activeDocUids ?? [],
    outcomes: overrides.outcomes ?? { failed: new Map(), resolved: new Set() },
    justCompletedDocUids: overrides.justCompletedDocUids ?? new Set(),
  });
}

describe("buildFolderRollups", () => {
  it("clears a snapshot-reported failure once the ranking says it was resolved", () => {
    // The rule that used to govern only the task source: a page loaded before a
    // cancel still carries the stale `failed` stage of a document the backend
    // has since erased.
    const rollups = rollupsFor({
      failedDocsByTagId: new Map([["t-a", [{ uid: "doc-a", name: "doc-a.pdf" }]]]),
      outcomes: { failed: new Map(), resolved: new Set(["doc-a"]) },
    });
    expect(rollups.get("A")?.failed).toEqual([]);
  });

  it("counts a document failing in both sources only once", () => {
    const rollups = rollupsFor({
      failedDocsByTagId: new Map([["t-a", [{ uid: "doc-a", name: "doc-a.pdf" }]]]),
      outcomes: { failed: new Map([["doc-a", { uid: "doc-a", name: "doc-a.pdf" }]]), resolved: new Set() },
    });
    expect(rollups.get("A")?.failed).toHaveLength(1);
  });

  it("marks a folder processing from either the loaded page or a live task", () => {
    expect(rollupsFor({ pendingTagIds: ["t-a"] }).get("A")?.processing).toBe(true);
    expect(rollupsFor({ activeDocUids: ["doc-a"] }).get("A")?.processing).toBe(true);
    expect(rollupsFor({}).get("A")?.processing).toBe(false);
  });

  it("ignores documents that belong to no visible folder", () => {
    const rollups = rollupsFor({
      outcomes: { failed: new Map([["ghost", { uid: "ghost", name: "ghost.pdf" }]]), resolved: new Set() },
    });
    expect(rollups.get("A")?.failed).toEqual([]);
  });

  it("reports a session completion on the folder holding the document", () => {
    expect(rollupsFor({ justCompletedDocUids: new Set(["doc-a"]) }).get("A")?.justDone).toBe(true);
  });
});
