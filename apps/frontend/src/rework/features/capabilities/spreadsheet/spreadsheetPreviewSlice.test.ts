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
  openSpreadsheet,
  registerSpreadsheet,
  spreadsheetPreviewSlice,
  type SpreadsheetPreviewState,
} from "./spreadsheetPreviewSlice";
import type { SpreadsheetPreviewPartData } from "./types";

const file = (id: string): SpreadsheetPreviewPartData => ({
  type: "spreadsheet_preview",
  preview_id: id,
  file_name: `${id}.xlsx`,
  xlsx_download_url: `/fs/download/${id}.xlsx`,
  preview_url: `/fs/download/${id}.preview.json`,
});

const { reducer } = spreadsheetPreviewSlice;
type Action = Parameters<typeof reducer>[1];
const reduce = (...actions: Action[]): SpreadsheetPreviewState =>
  actions.reduce<SpreadsheetPreviewState>(
    (state, action) => reducer(state, action),
    reducer(undefined, { type: "init" }),
  );

describe("spreadsheetPreviewSlice", () => {
  it("keeps the first registered file and lets an explicit open replace it", () => {
    const state = reduce(
      registerSpreadsheet({ sessionId: "s-1", preview: file("a") }),
      registerSpreadsheet({ sessionId: "s-1", preview: file("b") }),
    );
    expect(state.current?.preview_id).toBe("a");
    expect(reducer(state, openSpreadsheet({ sessionId: "s-1", preview: file("b") })).current?.preview_id).toBe("b");
  });

  it("resets when a card of another conversation registers", () => {
    const state = reduce(
      openSpreadsheet({ sessionId: "s-1", preview: file("a") }),
      registerSpreadsheet({ sessionId: "s-2", preview: file("c") }),
    );
    expect(state).toEqual({ sessionId: "s-2", current: file("c") });
  });
});
