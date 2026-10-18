// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { vi } from "vitest";

// Legacy knowledge-base fixtures exercise only the tag-backed source. Fail if
// they accidentally start a manager request instead of silently serving a fake page.
vi.mock("../../../../../slices/fredManager/fredManagerApiEnhancements", () => ({
  useListFoldersQuery: (_args: unknown, options: { skip: boolean }) => {
    if (!options.skip) throw new Error("Legacy fixture unexpectedly queried manager folders");
    return {};
  },
  useCreateFolderMutation: () => [vi.fn()],
  useRenameFolderMutation: () => [vi.fn()],
  useDeleteFolderMutation: () => [vi.fn()],
}));
