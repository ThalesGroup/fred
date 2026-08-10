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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import FilterChips from "@shared/molecules/FilterChips/FilterChips.tsx";
import PromptCard from "@shared/organisms/PromptCard/PromptCard.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import {
  type MarketplacePromptSummary,
  useGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery,
  useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery,
  usePostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostMutation,
  usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import PromptViewDialog from "../../PromptsPage/PromptViewDialog/PromptViewDialog.tsx";
import ImportPromptDialog from "./ImportPromptDialog/ImportPromptDialog.tsx";
import styles from "./MarketplacePrompts.module.scss";

const EDITOR_RELATIONS = new Set(["team_editor", "team_admin"]);

/** "Prompts de la communauté" — every published prompt across all teams, a
 * live view of the team rows. Actions: copy to clipboard (records a use),
 * import into one of the caller's spaces, and — for editors of the author
 * team — remove from the marketplace. */
export default function MarketplacePrompts() {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [search, setSearch] = useState("");
  const [activeTeam, setActiveTeam] = useState<string | null>(null);
  const [viewingPrompt, setViewingPrompt] = useState<MarketplacePromptSummary | null>(null);
  const [importingPrompt, setImportingPrompt] = useState<MarketplacePromptSummary | null>(null);
  const FILTER_VISIBLE = 4;

  const {
    data: prompts = [],
    isLoading,
    isUninitialized,
    isError,
  } = useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery();

  const [recordUse] = usePostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostMutation();
  const [unpublishPrompt] = usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation();

  // The listing carries only previews; fetch the full text on demand when a
  // card is opened, for the read-only view's copy-to-clipboard action.
  const { data: rawViewDetail } = useGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery(
    { promptId: viewingPrompt?.id || "" },
    { skip: !viewingPrompt },
  );
  // Guard against RTK Query serving the previous prompt's detail while the new
  // one is still in flight (same stale-result guard as PromptViewDialog).
  const viewDetail = rawViewDetail && rawViewDetail.id === viewingPrompt?.id ? rawViewDetail : undefined;

  // Teams the caller can edit → they may remove that team's prompts from the
  // marketplace directly from here (UX convenience).
  const editableTeamIds = useMemo(
    () =>
      new Set(
        availableTeams
          .filter((team) => (team.my_relations ?? []).some((relation) => EDITOR_RELATIONS.has(relation)))
          .map((team) => team.id),
      ),
    [availableTeams],
  );

  // One filter chip per distinct author team present in the marketplace.
  const teamChips = useMemo(() => {
    const byId = new Map<string, { id: string; label: string; count: number }>();
    for (const prompt of prompts) {
      const existing = byId.get(prompt.team_id);
      if (existing) existing.count += 1;
      else byId.set(prompt.team_id, { id: prompt.team_id, label: prompt.team_name, count: 1 });
    }
    return [...byId.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [prompts]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return prompts.filter((p) => {
      const matchSearch =
        !q ||
        p.name.toLowerCase().includes(q) ||
        (p.description ?? "").toLowerCase().includes(q) ||
        p.team_name.toLowerCase().includes(q);
      const matchTeam = !activeTeam || p.team_id === activeTeam;
      return matchSearch && matchTeam;
    });
  }, [prompts, search, activeTeam]);

  const handleRemoveFromMarketplace = (prompt: MarketplacePromptSummary) => {
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.marketplace.prompts.unpublish.title"),
      message: t("rework.marketplace.prompts.unpublish.message", { name: prompt.name }),
      confirmButtonLabel: t("rework.marketplace.prompts.unpublish.confirm"),
      onConfirm: async () => {
        try {
          await unpublishPrompt({ teamId: prompt.team_id, promptId: prompt.id }).unwrap();
          showSuccess({ summary: t("rework.marketplace.prompts.unpublish.successToast") });
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: t("rework.marketplace.prompts.unpublish.errorToast"),
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  // Only gate the full-page spinner on the initial load (no data yet) — a
  // background refetch (e.g. after recording a marketplace "use" on copy, or an
  // unpublish/import) must not blank the page and unmount the open dialog,
  // which caused a visible flicker. `isFetching` is intentionally omitted.
  const queryState = getQueryUiState({ isLoading, isUninitialized, isError });

  if (queryState === "loading") {
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.marketplace.prompts.loading")}
      </div>
    );
  }

  if (queryState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.controlPlane.title")}
        description={t("rework.serviceNotice.controlPlane.description")}
        centered
      />
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.marketplace.prompts.title")}</h1>
        <div className={styles.search}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t("rework.marketplace.prompts.searchPlaceholder")}
            clearAriaLabel={t("rework.marketplace.prompts.clearSearch")}
            size="small"
          />
        </div>
      </div>

      <div className={styles.content}>
        {teamChips.length > 0 && (
          <FilterChips
            options={teamChips}
            value={activeTeam}
            onChange={(v) => setActiveTeam(v)}
            allLabel={t("rework.teams.agents.podFilter.all")}
            maxVisible={FILTER_VISIBLE}
            showMoreLabel={(count) => `+${count}`}
            showLessLabel="−"
          />
        )}

        {prompts.length === 0 ? (
          <div className={styles.empty}>{t("rework.marketplace.prompts.empty")}</div>
        ) : filtered.length === 0 ? (
          <div className={styles.empty}>{t("rework.marketplace.prompts.emptySearch")}</div>
        ) : (
          <div className={styles.promptList}>
            {filtered.map((prompt) => (
              <PromptCard
                key={prompt.id}
                prompt={prompt}
                variant="marketplace"
                teamName={prompt.team_name}
                canRemoveFromMarketplace={editableTeamIds.has(prompt.team_id)}
                onView={() => setViewingPrompt(prompt)}
                onImport={() => setImportingPrompt(prompt)}
                onRemoveFromMarketplace={() => handleRemoveFromMarketplace(prompt)}
              />
            ))}
          </div>
        )}
      </div>

      <PromptViewDialog
        open={!!viewingPrompt}
        preloadedDetail={
          viewDetail
            ? {
                id: viewDetail.id,
                name: viewDetail.name,
                description: viewDetail.description,
                text: viewDetail.text,
              }
            : null
        }
        chipLabel={viewingPrompt?.team_name ?? null}
        onCopied={() => {
          if (viewingPrompt) recordUse({ promptId: viewingPrompt.id });
        }}
        onClose={() => setViewingPrompt(null)}
      />

      <ImportPromptDialog
        open={!!importingPrompt}
        promptId={importingPrompt?.id ?? null}
        promptName={importingPrompt?.name ?? ""}
        originTeamId={importingPrompt?.team_id ?? null}
        onClose={() => setImportingPrompt(null)}
      />
    </div>
  );
}
