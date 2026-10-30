// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { RuntimeExecuteRequest } from "../../../../slices/runtime/runtimeOpenApi";
import type { DocumentLibrarySelection } from "@shared/molecules/DocumentLibraryScopePicker/documentLibrarySelection";

/** One transport for the combined selection. Never mirror it in RuntimeContext:
 * the server intersects both representations, so a stale mirror would narrow reset. */
export function documentSelectionTurnOptions(
  selection: DocumentLibrarySelection | null,
): RuntimeExecuteRequest["turn_options"] {
  return {
    document_access: {
      library_tag_ids: selection?.folderIds ?? null,
      document_uids: selection?.documentIds ?? null,
    },
  };
}
