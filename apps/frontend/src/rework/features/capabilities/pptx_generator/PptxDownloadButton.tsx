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

// Download button for a generated deck's `.pptx`, shared by the chat card and pane header.
// Not a plain `<a download>`: the KF route is bearer-protected, so `downloadAuthed`
// fetches with the bearer and saves the blob client-side.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../utils/downloadUtils";

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
  const [isDownloading, setIsDownloading] = useState(false);

  const label = t("capability.pptx_generator.preview.download", { defaultValue: "Download .pptx" });

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      await downloadAuthed(href, fileName || "presentation.pptx");
    } catch (err) {
      showError({
        summary: t("capability.pptx_generator.preview.downloadError", { defaultValue: "Download failed" }),
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <Tooltip text={label}>
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        onClick={handleDownload}
        disabled={isDownloading}
        aria-label={label}
      />
    </Tooltip>
  );
}
