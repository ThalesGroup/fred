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

// "Download template" for the ppt_filler options, shared by the Advanced widget
// and the Simple view's pack — the same rule as the upload logic those two
// already share.
//
// It offers the SAVED template only: a file just picked is not what the agent
// will use until Save, and offering it here would hand back a different deck
// than the one being downloaded from.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadStoredTemplate, StoredTemplateMissingError } from "./templateDownload";

export function PptTemplateDownloadButton({
  teamId,
  agentInstanceId,
  agentDisplayName,
  hasPersistedTemplate,
  disabled,
}: {
  teamId?: string;
  /** Absent while the agent is being created — there is nothing stored to fetch. */
  agentInstanceId?: string;
  agentDisplayName?: string;
  hasPersistedTemplate: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [isDownloading, setIsDownloading] = useState(false);

  const canDownload = hasPersistedTemplate && Boolean(teamId) && Boolean(agentInstanceId);

  // A disabled button is unfocusable, so a `title` on it would never be
  // announced — the wrapper carries the reason instead, and it is a reason, not
  // a restatement of the label: "nothing to download yet" and "this hands back
  // the saved template, not the one you just picked" are what a reader asks.
  const hint = canDownload
    ? t("capability.ppt_filler.form.downloadTemplateHint")
    : t("capability.ppt_filler.form.downloadTemplateUnavailable");

  const handleDownload = async () => {
    if (!teamId || !agentInstanceId) return;
    setIsDownloading(true);
    try {
      await downloadStoredTemplate(teamId, agentInstanceId, agentDisplayName);
    } catch (err) {
      showError({
        summary:
          err instanceof StoredTemplateMissingError
            ? t("capability.ppt_filler.form.downloadMissing")
            : t("capability.ppt_filler.form.downloadFailed"),
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <span title={hint}>
      <Button
        color="primary"
        variant="outlined"
        size="small"
        disabled={disabled || isDownloading || !canDownload}
        icon={{ category: "outlined", type: "download" }}
        onClick={handleDownload}
        aria-label={`${t("capability.ppt_filler.form.downloadTemplate")} — ${hint}`}
      >
        {t("capability.ppt_filler.form.downloadTemplate")}
      </Button>
    </span>
  );
}
