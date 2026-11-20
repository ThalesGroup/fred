// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext } from "react";

export type PptBuilderUpload = {
  phase: "uploading" | "pending" | "running" | "succeeded" | "failed";
  draftId: string | null;
  error: string | null;
  summary: string | null;
  retry: (() => Promise<void>) | null;
  retrying: boolean;
};

export const PptBuilderUploadContext = createContext<PptBuilderUpload | null>(null);
