// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { documentSelectionTurnOptions } from "./documentSelectionTurnOptions";

describe("document selection transport", () => {
  it("unions folders and documents in the capability turn options", () => {
    expect(documentSelectionTurnOptions({ folderIds: ["folder"], documentIds: ["document"] })).toEqual({
      document_access: { library_tag_ids: ["folder"], document_uids: ["document"] },
    });
  });
  it("keeps removing the last document distinct from resetting to the agent", () => {
    expect(documentSelectionTurnOptions({ folderIds: [], documentIds: [] })).toEqual({
      document_access: { library_tag_ids: [], document_uids: [] },
    });
    expect(documentSelectionTurnOptions(null)).toEqual({
      document_access: { library_tag_ids: null, document_uids: null },
    });
  });
});
