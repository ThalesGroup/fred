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

/**
 * PptxDownloadButton
 * ------------------
 * Download icon button for a filled deck's source `.pptx`. Used by BOTH the in-chat
 * preview card and the preview pane header so the two stay DRY and identical.
 *
 * Why not a plain `<a href download>`: the deck lives behind the bearer-protected
 * Knowledge Flow `/storage/user/{key}` endpoint. A bare anchor sends no Authorization
 * header, so the browser navigation gets a 401 and "the file wasn't available". We
 * instead fetch the bytes WITH the bearer (RTK `downloadHrefBlob`, same path the
 * writable-document export uses) and trigger a client-side blob download — which also
 * guarantees the correct file name regardless of storage headers.
 *
 * Built with the rework design system (shared IconButton + Tooltip), not MUI.
 */

import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useLazyDownloadHrefBlobQuery } from "../../slices/knowledgeFlow/knowledgeFlowApi.blob.ts";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";

export default function PptxDownloadButton({
  href,
  fileName,
}: {
  /** Bearer-protected KF href for the `.pptx` (the part's `pptx_download_url`). */
  href: string;
  /** Suggested download file name (the part's `file_name`). */
  fileName?: string | null;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [downloadHref, { isFetching }] = useLazyDownloadHrefBlobQuery();

  const label = t("chat.pptPreview.download", "Download .pptx");

  const handleDownload = async () => {
    try {
      const blob = await downloadHref({ href }).unwrap();
      downloadFile(blob, fileName || "presentation.pptx");
    } catch (err: any) {
      showError({
        summary: t("chat.pptPreview.downloadError", "Download failed"),
        detail: err?.message || String(err),
      });
    }
  };

  return (
    <Tooltip text={label}>
      <IconButton
        color="on-surface"
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        onClick={handleDownload}
        disabled={isFetching}
        aria-label={label}
      />
    </Tooltip>
  );
}
