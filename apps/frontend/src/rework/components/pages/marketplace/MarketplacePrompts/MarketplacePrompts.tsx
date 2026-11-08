// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useNavigate } from "react-router-dom";
import Select from "@shared/molecules/Select/Select";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
import PromptCard from "@shared/organisms/PromptCard/PromptCard";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  usePublishedPromptsQuery,
  usePromptPublicationSpacesQuery,
  useSetPromptPublicationMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PublishedPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import PromptViewDialog from "../../PromptsPage/PromptViewDialog/PromptViewDialog";
import PromptMarketplaceScope from "./PromptMarketplaceScope";
import styles from "./MarketplacePrompts.module.scss";

export default function MarketplacePrompts() {
  return (
    <PromptMarketplaceScope>
      {(marketplaceSpaceId) => <MarketplaceContents key={marketplaceSpaceId} marketplaceSpaceId={marketplaceSpaceId} />}
    </PromptMarketplaceScope>
  );
}

function MarketplaceContents({ marketplaceSpaceId }: { marketplaceSpaceId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const spacesQuery = usePromptPublicationSpacesQuery(
    {},
    { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(spacesQuery.refetch, false);
  const publishingSpaces = spacesQuery.isError
    ? []
    : (spacesQuery.currentData?.items ?? []).filter((space) =>
        space.marketplace_space_ids.includes(marketplaceSpaceId),
      );
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [search, setSearch] = useState("");
  const [activeSpace, setActiveSpace] = useState<string | null>(null);
  const [viewingId, setViewingId] = useState<string>();
  const catalog = usePublishedPromptsQuery(
    { marketplaceSpaceId },
    { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(catalog.refetch, false);
  const prompts = catalog.currentData?.items;
  const [setPublication] = useSetPromptPublicationMutation();
  const sources = useMemo(() => {
    const byId = new Map<string, { id: string; label: string }>();
    for (const prompt of prompts ?? [])
      byId.set(prompt.space_id, { id: prompt.space_id, label: prompt.source_space_name });
    return [...byId.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [prompts]);
  const filtered = (prompts ?? []).filter((prompt) => {
    const query = search.trim().toLowerCase();
    return (
      (!activeSpace || prompt.space_id === activeSpace) &&
      (!query ||
        [prompt.display_name, prompt.description, prompt.logical_name, prompt.source_space_name, ...prompt.tags].some(
          (value) => value?.toLowerCase().includes(query),
        ))
    );
  });
  const remove = (prompt: PublishedPromptSummary) => {
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.marketplace.prompts.unpublish.title"),
      message: t("rework.marketplace.prompts.unpublish.message", { name: prompt.display_name }),
      confirmButtonLabel: t("rework.marketplace.prompts.unpublish.confirm"),
      onConfirm: async () => {
        try {
          await setPublication({
            spaceId: prompt.space_id,
            promptId: prompt.prompt_id,
            marketplaceSpaceId,
            promptPublicationRequest: { published: false },
          }).unwrap();
          setViewingId(undefined);
          showSuccess({ summary: t("rework.marketplace.prompts.unpublish.successToast") });
        } catch {
          setViewingId(undefined);
          showError({ summary: t("rework.marketplace.prompts.unpublish.errorToast") });
        }
      },
    });
  };

  if (catalog.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} centered />;
  if (!prompts)
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.marketplace.prompts.loading")}
      </div>
    );
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.marketplace.prompts.title")}</h1>
        <div className={styles.search}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t("rework.marketplace.prompts.searchPlaceholder")}
            ariaLabel={t("rework.marketplace.prompts.searchPlaceholder")}
            clearAriaLabel={t("rework.marketplace.prompts.clearSearch")}
            size="small"
          />
        </div>
      </div>
      <div className={styles.content}>
        {publishingSpaces.length > 0 && (
          <Select
            size="small"
            compact
            label={t("rework.promptPublication.libraries")}
            placeholder={t("rework.promptPublication.libraries")}
            options={publishingSpaces.map((space) => ({ key: space.id, value: space.id, label: space.name }))}
            onChange={(id) => navigate(`/team/${id}/prompts`)}
          />
        )}

        <FilterChips
          options={sources}
          value={activeSpace}
          onChange={setActiveSpace}
          allLabel={t("rework.teams.agents.podFilter.all")}
          maxVisible={4}
          aria-label={t("rework.sidebar.team.spaceLabel")}
        />
        {catalog.isFetching && !catalog.currentData ? (
          <Spinner size={20} />
        ) : filtered.length === 0 ? (
          <div className={styles.empty}>
            {t(prompts.length ? "rework.marketplace.prompts.emptySearch" : "rework.marketplace.prompts.empty")}
          </div>
        ) : (
          <div className={styles.promptList}>
            {filtered.map((prompt) => (
              <PromptCard
                key={prompt.prompt_id}
                prompt={prompt}
                variant="marketplace"
                teamName={prompt.source_space_name}
                canRemoveFromMarketplace={prompt.can_publish}
                onView={() => setViewingId(prompt.prompt_id)}
                onRemoveFromMarketplace={() => remove(prompt)}
              />
            ))}
          </div>
        )}
      </div>
      <PromptViewDialog
        open={!!viewingId && prompts.some((prompt) => prompt.prompt_id === viewingId)}
        marketplaceSpaceId={marketplaceSpaceId}
        promptId={viewingId}
        onClose={() => setViewingId(undefined)}
      />
    </div>
  );
}
