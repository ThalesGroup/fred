// useAssetDownloader.tsx
// Copyright Thales 2025
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

// Centralized helper to download user assets via the knowledge-flow API (Blob).

import { useCallback } from "react";
import type { LinkPart } from "../../slices/agentic/agenticOpenApi.ts";
import { useLazyDownloadHrefBlobQuery } from "../../slices/knowledgeFlow/knowledgeFlowApi.blob.ts";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";

export const workspaceUserFileDownloader = () => {
  const { showError } = useToast();
  const [downloadByHref] = useLazyDownloadHrefBlobQuery();

  const downloadLink = useCallback(
    async (link: LinkPart) => {
      if (!link.href) {
        showError({ summary: "Download error", detail: "Missing download URL." });
        return;
      }

      try {
        const blob = await downloadByHref({
          href: link.href,
          assetOwnerId: link.rel || undefined, // optional override header
        }).unwrap();

        downloadFile(blob, link.file_name || link.title || "download");
      } catch (err: any) {
        console.error("Failed to download asset link", err);
        showError({
          summary: "Download error",
          detail: err?.message || "Download failed.",
        });
      }
    },
    [downloadByHref, showError],
  );

  return { downloadLink };
};
