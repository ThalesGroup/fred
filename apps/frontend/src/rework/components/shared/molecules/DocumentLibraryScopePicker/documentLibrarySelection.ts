// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { Document, Folder } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

/** UI value shared by agent configuration and conversation. Folder ids cover
 * direct members, unioned with explicit document ids. Picking a subtree adds
 * each existing folder, matching Swift's selection algebra. These are Weaver
 * ids, not Knowledge Flow tags. This value is not an authorization grant. */
export interface DocumentLibrarySelection {
  folderIds: Folder["id"][];
  documentIds: Document["id"][];
}

/** Shared activation for the form, chat controls and selection transport. */
export const DOCUMENT_SELECTION_SUPPORTED = true;
