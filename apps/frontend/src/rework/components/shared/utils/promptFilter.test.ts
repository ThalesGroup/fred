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
import { filterPrompts, NO_CATEGORY_FILTER_ID, type FilterablePrompt } from "./promptFilter";

const ALL = { search: "", categoryId: null };

const WEEKLY: FilterablePrompt & { id: string } = {
  id: "p-1",
  name: "Weekly report",
  description: "Summarises the sprint",
  category_id: "cat-report",
};
const ONBOARD: FilterablePrompt & { id: string } = {
  id: "p-2",
  name: "Onboarding checklist",
  description: "Steps for a new joiner",
  category_id: "cat-hr",
};
const LOOSE: FilterablePrompt & { id: string } = {
  id: "p-3",
  name: "Scratch",
  description: null,
  category_id: null,
};

const LIST = [WEEKLY, ONBOARD, LOOSE];

function ids(prompts: Array<{ id: string }>): string[] {
  return prompts.map((p) => p.id);
}

describe("filterPrompts", () => {
  it("returns everything with no search and no category", () => {
    expect(ids(filterPrompts(LIST, ALL))).toEqual(["p-1", "p-2", "p-3"]);
  });

  it("treats a whitespace-only search as empty", () => {
    // The panel passes the raw input value through.
    expect(ids(filterPrompts(LIST, { ...ALL, search: "   " }))).toEqual(["p-1", "p-2", "p-3"]);
  });

  it("matches the name case-insensitively", () => {
    expect(ids(filterPrompts(LIST, { ...ALL, search: "WEEKLY" }))).toEqual(["p-1"]);
  });

  it("matches the description too", () => {
    expect(ids(filterPrompts(LIST, { ...ALL, search: "joiner" }))).toEqual(["p-2"]);
  });

  it("tolerates a null description", () => {
    expect(ids(filterPrompts(LIST, { ...ALL, search: "scratch" }))).toEqual(["p-3"]);
  });

  it("filters by category id", () => {
    expect(ids(filterPrompts(LIST, { ...ALL, categoryId: "cat-hr" }))).toEqual(["p-2"]);
  });

  it("selects only uncategorised prompts under the sentinel id", () => {
    expect(ids(filterPrompts(LIST, { ...ALL, categoryId: NO_CATEGORY_FILTER_ID }))).toEqual(["p-3"]);
  });

  it("applies search and category together, not either/or", () => {
    // "report" matches p-1's name; the HR category excludes it.
    expect(filterPrompts(LIST, { search: "report", categoryId: "cat-hr" })).toEqual([]);
    expect(ids(filterPrompts(LIST, { search: "report", categoryId: "cat-report" }))).toEqual(["p-1"]);
  });

  it("treats a prompt whose category no longer exists as uncategorised", () => {
    // A category can be deleted while prompts still point at it; without this
    // the prompt would answer to no chip at all.
    const orphan = { id: "p-4", name: "Orphan", category_id: "cat-deleted" };
    const known = new Set(["cat-report", "cat-hr"]);

    expect(
      ids(filterPrompts([orphan], { ...ALL, categoryId: NO_CATEGORY_FILTER_ID, knownCategoryIds: known })),
    ).toEqual(["p-4"]);
    // Without the set, the id is trusted as-is and the prompt is categorised.
    expect(filterPrompts([orphan], { ...ALL, categoryId: NO_CATEGORY_FILTER_ID })).toEqual([]);
  });

  it("still excludes a live category from the uncategorised chip", () => {
    const known = new Set(["cat-report", "cat-hr"]);
    expect(filterPrompts([WEEKLY], { ...ALL, categoryId: NO_CATEGORY_FILTER_ID, knownCategoryIds: known })).toEqual([]);
  });

  it("preserves the incoming order", () => {
    expect(ids(filterPrompts([LOOSE, WEEKLY], ALL))).toEqual(["p-3", "p-1"]);
  });

  it("does not let a query span the name/description boundary", () => {
    expect(filterPrompts([WEEKLY], { ...ALL, search: "reportsummarises" })).toEqual([]);
  });
});
