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

// Downloads the `.xlsx` with the live bearer (a bare anchor would 401 on the
// protected `/fs/download` route). An icon button in the chat card, a labelled
// button in the pane header.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../utils/downloadUtils";

interface SpreadsheetDownloadButtonProps {
  href: string;
  fileName: string;
  labelled?: boolean;
}

export default function SpreadsheetDownloadButton({
  href,
  fileName,
  labelled = false,
}: SpreadsheetDownloadButtonProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [busy, setBusy] = useState(false);
  const label = t("capability.spreadsheet.download");

  const download = async () => {
    setBusy(true);
    try {
      await downloadAuthed(href, fileName);
    } catch (err) {
      showError({
        summary: t("capability.spreadsheet.downloadError"),
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(false);
    }
  };

  const icon = { category: "outlined", type: "download" } as const;
  if (labelled) {
    return (
      <Button color="primary" variant="text" size="small" icon={icon} onClick={download} disabled={busy}>
        {label}
      </Button>
    );
  }
  return (
    <Tooltip text={label}>
      <IconButton variant="icon" size="medium" icon={icon} onClick={download} disabled={busy} aria-label={label} />
    </Tooltip>
  );
}
