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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap";
import { usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ImportPromptDialog.module.scss";

interface ImportPromptDialogProps {
  open: boolean;
  promptId: string | null;
  promptName: string;
  onClose: () => void;
}

const EDITOR_RELATIONS = new Set(["team_editor", "team_admin"]);

/** Multi-select target picker for importing a marketplace prompt into the
 * caller's own spaces: the personal space plus every team the caller can edit.
 * Import is a copy-by-value, so each target lands with a reset counter and an
 * `_imported-N` name (handled server-side). */
export default function ImportPromptDialog({ open, promptId, promptName, onClose }: ImportPromptDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [importPrompt, { isLoading }] =
    usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation();

  const personalId = activeTeam?.id ?? "personal";

  // Teams the caller can edit (excluding the personal space, which is always
  // offered separately at the top).
  const editableTeams = useMemo(
    () =>
      availableTeams.filter(
        (team) =>
          !isPersonalTeamId(team.id) &&
          team.id !== personalId &&
          (team.my_relations ?? []).some((relation) => EDITOR_RELATIONS.has(relation)),
      ),
    [availableTeams, personalId],
  );

  const filteredTeams = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return editableTeams;
    return editableTeams.filter((team) => team.name.toLowerCase().includes(q));
  }, [editableTeams, search]);

  useEffect(() => {
    if (open) {
      setSelected(new Set());
      setSearch("");
    }
  }, [open]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirm = async () => {
    if (!promptId || selected.size === 0) return;
    try {
      const response = await importPrompt({
        promptId,
        marketplaceImportRequest: { target_team_ids: [...selected] },
      }).unwrap();
      const ok = response.results.filter((r) => r.prompt).length;
      const failed = response.results.filter((r) => r.error);
      if (ok > 0) showSuccess({ summary: t("rework.marketplace.prompts.import.successToast", { count: ok }) });
      if (failed.length > 0) {
        showError({
          summary: t("rework.marketplace.prompts.import.errorToast", { count: failed.length }),
          detail: failed.map((r) => r.error).join(" · "),
        });
      }
      onClose();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: t("rework.marketplace.prompts.import.errorToast", { count: selected.size }),
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  return (
    <Dialog
      open={open}
      title={t("rework.marketplace.prompts.import.title")}
      confirmLabel={t("rework.marketplace.prompts.import.confirm")}
      confirmDisabled={selected.size === 0 || isLoading}
      onConfirm={handleConfirm}
      onCancel={onClose}
    >
      <div className={styles.container}>
        <p className={styles.subtitle}>{t("rework.marketplace.prompts.import.subtitle", { name: promptName })}</p>

        {/* Personal space is always available (the caller is its editor). */}
        <label className={styles.row}>
          <Checkbox checked={selected.has(personalId)} onChange={() => toggle(personalId)} />
          <span className={styles.rowLabel}>{t("rework.marketplace.prompts.import.personalSpace")}</span>
        </label>

        {editableTeams.length > 0 && (
          <>
            <div className={styles.searchBar}>
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t("rework.marketplace.prompts.import.searchPlaceholder")}
                clearAriaLabel={t("rework.marketplace.prompts.import.clearSearch")}
                size="xs"
              />
            </div>
            <div className={styles.teamList}>
              {filteredTeams.map((team) => (
                <label key={team.id} className={styles.row}>
                  <Checkbox checked={selected.has(team.id)} onChange={() => toggle(team.id)} />
                  <span className={styles.rowLabel}>{team.name}</span>
                </label>
              ))}
              {filteredTeams.length === 0 && (
                <p className={styles.empty}>{t("rework.marketplace.prompts.import.noTeams")}</p>
              )}
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
