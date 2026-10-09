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

import { useTranslation } from "react-i18next";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import CopyToTeamsDialog from "@shared/organisms/CopyToTeamsDialog/CopyToTeamsDialog.tsx";
import { usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

interface ImportPromptDialogProps {
  open: boolean;
  promptId: string | null;
  promptName: string;
  /** The prompt's author team — shown in the list but not importable into. */
  originTeamId?: string | null;
  onClose: () => void;
}

/** Imports a marketplace prompt into the caller's own spaces. Import is a
 * copy-by-value, so each target lands with a reset counter and an
 * `_imported-N` name (handled server-side). */
export default function ImportPromptDialog({
  open,
  promptId,
  promptName,
  originTeamId,
  onClose,
}: ImportPromptDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const [importPrompt, { isLoading }] =
    usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation();

  const handleConfirm = async (teamIds: string[]) => {
    if (!promptId || teamIds.length === 0) return;
    try {
      const response = await importPrompt({
        promptId,
        marketplaceImportRequest: { target_team_ids: teamIds },
      }).unwrap();
      const ok = response.results.filter((r) => r.prompt).length;
      const failed = response.results.filter((r) => r.error);
      if (ok > 0) showSuccess({ summary: t("rework.marketplace.prompts.import.successToast", { count: ok }) });
      if (failed.length > 0) {
        showError({
          summary: t("rework.marketplace.prompts.import.errorToast", { count: failed.length }),
          detail: failed
            .map((r) =>
              r.error_code === "prompt_command_reserved" ? t("rework.teams.prompts.form.commandReserved") : r.error,
            )
            .join(" · "),
        });
      }
      onClose();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: t("rework.marketplace.prompts.import.errorToast", { count: teamIds.length }),
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  return (
    <CopyToTeamsDialog
      open={open}
      title={t("rework.marketplace.prompts.import.title")}
      subtitle={t("rework.marketplace.prompts.import.subtitle", { name: promptName })}
      confirmLabel={t("rework.marketplace.prompts.import.confirm")}
      // Editing a team's prompts needs `team_editor`; holding only
      // `team_admin` leaves the list empty, so say why.
      noEditableTeamsLabel={t("rework.marketplace.prompts.import.noEditableTeams")}
      originTeamId={originTeamId}
      isSubmitting={isLoading}
      onConfirm={(teamIds) => void handleConfirm(teamIds)}
      onClose={onClose}
    />
  );
}
