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

// A dropped directory targets one folder per subdirectory, so the same leaf
// name can conflict in two of them at once and each needs its own answer.
// These pin that the destination is part of a decision's identity.

import { describe, expect, it } from "vitest";

import {
  conflictKey,
  conflictsToAsk,
  decisionsForGroup,
  destinationsToCheck,
  namesArrivingTwice,
  splitByDecision,
  type ConflictDecision,
  type UploadGroup,
} from "./importConflicts";

const file = (path: string) => new File(["x"], path);
const leaf = (f: File) => f.name.split("/").pop() || f.name;

const groups: UploadGroup[] = [
  { tagId: "tag-jan", files: [file("2026/jan/report.pdf"), file("2026/jan/notes.md")] },
  { tagId: "tag-feb", files: [file("2026/feb/report.pdf")] },
  { tagId: null, files: [file("loose.pdf")] },
];

describe("destinationsToCheck", () => {
  it("asks once per folder, and not about a destination with no folder", () => {
    expect(destinationsToCheck(groups)).toEqual([
      { tag_id: "tag-jan", names: ["report.pdf", "notes.md"] },
      { tag_id: "tag-feb", names: ["report.pdf"] },
    ]);
  });

  it("does not repeat a name a batch happens to carry twice", () => {
    const repeated: UploadGroup[] = [{ tagId: "tag-jan", files: [file("a/x.pdf"), file("b/x.pdf")] }];
    expect(destinationsToCheck(repeated)).toEqual([{ tag_id: "tag-jan", names: ["x.pdf"] }]);
  });
});

describe("conflictsToAsk", () => {
  it("raises the same name once per folder that holds it", () => {
    const conflicts = conflictsToAsk(
      groups,
      [
        { tag_id: "tag-jan", names: ["report.pdf"] },
        { tag_id: "tag-feb", names: ["report.pdf"] },
      ],
      (f) => f.name,
    );

    expect(conflicts).toEqual([
      { tagId: "tag-jan", name: "report.pdf", label: "2026/jan/report.pdf" },
      { tagId: "tag-feb", name: "report.pdf", label: "2026/feb/report.pdf" },
    ]);
  });

  it("says nothing about folders the answer did not name", () => {
    expect(conflictsToAsk(groups, [], (f) => f.name)).toEqual([]);
  });
});

describe("splitByDecision and decisionsForGroup", () => {
  const decisions = new Map<string, ConflictDecision>([
    [conflictKey("tag-jan", "report.pdf"), "overwrite"],
    [conflictKey("tag-feb", "report.pdf"), "skip"],
  ]);

  it("answers the same name differently in two folders", () => {
    const jan = splitByDecision(groups[0], decisions);
    const feb = splitByDecision(groups[1], decisions);

    expect(jan.toUpload.map(leaf)).toEqual(["report.pdf", "notes.md"]);
    expect(jan.skipped).toEqual([]);
    expect(feb.toUpload).toEqual([]);
    expect(feb.skipped.map(leaf)).toEqual(["report.pdf"]);
  });

  it("gives each request only the decisions about its own destination", () => {
    expect(decisionsForGroup(groups[0], decisions)).toEqual({ "report.pdf": "overwrite" });
    expect(decisionsForGroup(groups[1], decisions)).toEqual({ "report.pdf": "skip" });
    // A destination with no folder can hold no conflict, so it carries none.
    expect(decisionsForGroup(groups[2], decisions)).toEqual({});
  });
});

describe("namesArrivingTwice", () => {
  it("reports a name one folder would receive twice", () => {
    const colliding: UploadGroup[] = [{ tagId: "tag-jan", files: [file("a/report.pdf"), file("b/report.pdf")] }];
    expect(namesArrivingTwice(colliding)).toEqual(["report.pdf"]);
  });

  it("says nothing when the two land in different folders", () => {
    // groups already carries report.pdf into tag-jan and tag-feb.
    expect(namesArrivingTwice(groups)).toEqual([]);
  });

  it("groups destinations with no folder together", () => {
    const rootless: UploadGroup[] = [
      { tagId: null, files: [file("x.pdf")] },
      { tagId: null, files: [file("x.pdf")] },
    ];
    expect(namesArrivingTwice(rootless)).toEqual(["x.pdf"]);
  });
});
