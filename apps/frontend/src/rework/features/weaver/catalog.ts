// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
/** One small port per entry. A preview is not evidence of a working Weaver feature. */
export const weaverFeatures = [
  { id: "audit", preview: "/admin/corpus-audit" },
  { id: "tasks", preview: "/admin/tasks" },
  { id: "diagnostics", preview: "/admin/self-test" },
  { id: "migration", preview: "/admin/migration" },
  { id: "knowledge-bases", preview: "/team/preview-team/knowledge-bases" },
  { id: "knowledge-documents", preview: "/team/preview-team/knowledge-bases/preview-kb" },
  { id: "documents", preview: "/documents" },
  { id: "dictation", preview: "/dictation" },
] as const;
export type WeaverFeature = (typeof weaverFeatures)[number]["id"];
