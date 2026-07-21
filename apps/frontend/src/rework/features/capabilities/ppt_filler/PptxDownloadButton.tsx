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

// Download icon button for a filled deck's source `.pptx`, shared by BOTH the
// in-chat preview card and the preview pane header so the two stay DRY.
//
// Why not a plain `<a href download>`: the deck lives behind the bearer-protected
// Knowledge Flow `/fs/download` route. A bare anchor sends no Authorization header,
// so the navigation 401s. `downloadAuthed` fetches the bytes WITH the live bearer,
// then triggers a client-side blob save — the sanctioned pattern (ArtifactLinkChip).

import { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../utils/downloadUtils";

export default function PptxDownloadButton({
  href,
  fileName,
}: {
  /** Bearer-protected KF href for the `.pptx` (the part's `pptx_download_url`). */
  href: string;
  /** Suggested download file name (the part's `file_name`). */
  fileName?: string;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [isDownloading, setIsDownloading] = useState(false);

  const label = t("capability.ppt_filler.preview.download", { defaultValue: "Download .pptx" });

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      await downloadAuthed(href, fileName || "presentation.pptx");
    } catch (err) {
      showError({
        summary: t("capability.ppt_filler.preview.downloadError", { defaultValue: "Download failed" }),
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <IconButton
      color="on-surface"
      variant="icon"
      size="small"
      icon={{ category: "outlined", type: "download" }}
      onClick={handleDownload}
      disabled={isDownloading}
      aria-label={label}
    />
  );
}
