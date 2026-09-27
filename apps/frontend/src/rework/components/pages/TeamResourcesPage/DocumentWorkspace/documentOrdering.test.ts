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
import {
  DEFAULT_ORDERING,
  SORTABLE_COLUMN_KEYS,
  orderingFromSortState,
  sortStateFromOrdering,
  type DocumentSortField,
} from "./documentOrdering";

// Stands in for the component's `t(SORTABLE_COLUMN_KEYS[field])`.
const label = (field: DocumentSortField) => `label:${field}`;

describe("orderingFromSortState", () => {
  it("maps a sorted column back to its contract field", () => {
    expect(orderingFromSortState({ columnLabel: "label:created", direction: "desc" }, label)).toEqual({
      by: "created",
      order: "desc",
    });
  });

  it("returns to the default on the header's third press", () => {
    // DataTable cycles asc -> desc -> null, and there is no unordered state to
    // ask the server for: a page is always cut out of some order.
    expect(orderingFromSortState(null, label)).toEqual(DEFAULT_ORDERING);
  });

  it("falls back to the default for a label it does not know", () => {
    // A column renamed, or made sortable without being declared — the list
    // stays ordered by something rather than by whatever the store returns.
    expect(orderingFromSortState({ columnLabel: "Ajouté par", direction: "asc" }, label)).toEqual(DEFAULT_ORDERING);
  });
});

describe("sortStateFromOrdering", () => {
  it("names the column the header must show the arrow on", () => {
    expect(sortStateFromOrdering({ by: "size", order: "asc" }, label)).toEqual({
      columnLabel: "label:size",
      direction: "asc",
    });
  });

  it("round-trips every sortable field in both directions", () => {
    for (const by of Object.keys(SORTABLE_COLUMN_KEYS) as DocumentSortField[]) {
      for (const order of ["asc", "desc"] as const) {
        expect(orderingFromSortState(sortStateFromOrdering({ by, order }, label), label)).toEqual({ by, order });
      }
    }
  });
});

describe("the sortable column set", () => {
  it("leaves out the uploader column", () => {
    // `uploaded_by` is optional: ordering on it would bunch every older or
    // connector-pulled document at one end under a dash.
    expect(Object.keys(SORTABLE_COLUMN_KEYS)).toEqual(["name", "created", "size"]);
  });

  it("defaults to name ascending, the file-explorer convention", () => {
    expect(DEFAULT_ORDERING).toEqual({ by: "name", order: "asc" });
  });
});
